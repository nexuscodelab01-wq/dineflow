"""POS: device pairing, PIN quick-switch, counter orders, cash tender.

Counter orders are paid *before* they reach the kitchen — the normal quick-service counter pattern
(unlike a table's tab, which is correctly the opposite: open all meal, pay at the end via
TableSessionService.place_round/mark_paid_cash). So create_counter_order leaves the order PENDING and
never publishes to the kitchen; mark_counter_order_paid_cash is what actually confirms it, reusing
OrderService.confirm_payment — the exact same PENDING -> CONFIRMED + kitchen-publish + (no-op, no
customer_email) confirmation-email transition every online order already goes through. The order row
has to exist before payment can reference it (an order_id), but nothing about it is visible to kitchen
staff — or counted as revenue, since analytics/dashboard queries already only count CONFIRMED+ orders —
until that happens.
"""

import secrets
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.core.security import (
    POS_SESSION_MINUTES,
    create_device_token,
    create_pos_session_token,
    hash_password,
    verify_password,
)
from app.models.audit_log import AuditLog
from app.models.device import TILL, Device
from app.models.enums import OrderStatus, OrderType, PaymentMethod, PaymentStatus
from app.models.loyalty import LoyaltyAccount
from app.models.menu_item import MenuItem
from app.models.order import Order
from app.models.order_status_history import OrderStatusHistory
from app.models.payment import Payment
from app.models.restaurant import Restaurant
from app.models.restaurant_user import RestaurantUser
from app.models.user import User
from app.schemas.pos import (
    AvailabilityRead,
    DevicePairResponse,
    DeviceRead,
    PinLoginResponse,
    PosCardIntentRead,
    PosCouponPreviewRead,
    PosCouponPreviewRequest,
    PosCustomerRead,
    PosOrderCreate,
    PosOrderRead,
)
from app.services.feature_service import FeatureService
from app.services.order_service import OrderService
from app.services.payments import get_payment_provider
from app.services.shift_service import ShiftService
from app.services.tax import price_order_tax, service_charge_for

FEATURE = "pos"


class PosService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------ pairing (admin-facing)

    def pair_device(self, restaurant_id: int, label: str, admin: User, kind: str = TILL) -> DevicePairResponse:
        device = Device(restaurant_id=restaurant_id, label=label, kind=kind, paired_by_user_id=admin.id)
        self.db.add(device)
        self.db.flush()
        self.db.add(AuditLog(restaurant_id=restaurant_id, actor_user_id=admin.id, actor_label=admin.email, action="device.paired", target=label, details={"kind": kind}))
        self.db.commit()
        token = create_device_token(device.id, restaurant_id)
        return DevicePairResponse(device_id=device.id, label=device.label, kind=device.kind, device_token=token)

    def list_devices(self, restaurant_id: int) -> list[DeviceRead]:
        devices = self.db.scalars(select(Device).where(Device.restaurant_id == restaurant_id).order_by(Device.created_at.desc())).all()
        return [
            DeviceRead(
                id=d.id, label=d.label, kind=d.kind, paired_by_label=d.paired_by.email if d.paired_by else None,
                revoked_at=d.revoked_at, last_seen_at=d.last_seen_at, created_at=d.created_at,
            )
            for d in devices
        ]

    def revoke_device(self, restaurant_id: int, device_id: int, admin: User) -> None:
        device = self.db.get(Device, device_id)
        if device is None or device.restaurant_id != restaurant_id:
            raise NotFoundError("Device not found")
        if device.revoked_at is None:
            device.revoked_at = datetime.now(UTC)
            device.revoked_by_user_id = admin.id
            self.db.add(AuditLog(restaurant_id=restaurant_id, actor_user_id=admin.id, actor_label=admin.email, action="device.revoked", target=device.label))
        self.db.commit()

    # ------------------------------------------------------------------ PIN quick-switch

    def set_pin(self, restaurant_id: int, membership_id: int, pin: str, admin: User) -> None:
        membership = self.db.get(RestaurantUser, membership_id)
        if membership is None or membership.restaurant_id != restaurant_id:
            raise NotFoundError("Staff member not found")
        others = self.db.scalars(
            select(RestaurantUser).where(RestaurantUser.restaurant_id == restaurant_id, RestaurantUser.id != membership_id, RestaurantUser.is_active.is_(True))
        )
        new_hash = hash_password(pin)
        for other in others:
            if other.pin_hash and verify_password(pin, other.pin_hash):
                raise ConflictError("Another staff member already uses this PIN here")
        membership.pin_hash = new_hash
        self.db.add(AuditLog(restaurant_id=restaurant_id, actor_user_id=admin.id, actor_label=admin.email, action="pos.pin_set", target=f"membership:{membership_id}"))
        self.db.commit()

    def pin_login(self, device: Device, pin: str) -> PinLoginResponse:
        memberships = self.db.scalars(
            select(RestaurantUser).where(RestaurantUser.restaurant_id == device.restaurant_id, RestaurantUser.is_active.is_(True), RestaurantUser.pin_hash.is_not(None))
        )
        match = next((m for m in memberships if m.pin_hash and verify_password(pin, m.pin_hash)), None)
        if match is None:
            raise AppError("Incorrect PIN")
        user = self.db.get(User, match.user_id)
        if user is None or not user.is_active:
            raise AppError("Incorrect PIN")
        self.db.add(AuditLog(restaurant_id=device.restaurant_id, actor_user_id=user.id, actor_label=user.email, action="pos.pin_login", target=f"device:{device.id}"))
        self.db.commit()
        token = create_pos_session_token(device.id, user.id, device.restaurant_id)
        restaurant = self.db.get(Restaurant, device.restaurant_id)
        return PinLoginResponse(
            pos_session_token=token, staff_name=user.first_name, device_kind=device.kind,
            currency=restaurant.currency if restaurant else "usd", country=restaurant.country if restaurant else "US",
            tips_enabled=bool(restaurant and restaurant.tips_enabled),
            controls_enabled=FeatureService(self.db).is_enabled(device.restaurant_id, "pos_controls"),
            expires_in=POS_SESSION_MINUTES * 60,
        )

    # ------------------------------------------------------------------ counter orders

    def create_counter_order(self, restaurant_id: int, staff: User, data: PosOrderCreate) -> PosOrderRead:
        FeatureService(self.db).require(restaurant_id, FEATURE)
        restaurant = self.db.get(Restaurant, restaurant_id)
        if restaurant is None:
            raise NotFoundError("Restaurant not found")

        orders = OrderService(self.db)
        with self.db.begin_nested():
            item_ids = [line.menu_item_id for line in data.items]
            menu_items = orders.menu.get_items_by_ids(item_ids, restaurant.id)
            items_by_id = {item.id: item for item in menu_items}
            if len(items_by_id) != len(set(item_ids)):
                raise AppError("One or more menu items are invalid for this restaurant")

            customer = self._customer(restaurant.id, data.customer_id) if data.customer_id else None
            order = Order(
                # A looked-up customer owns the order (so loyalty follows them); otherwise it's the staff member's, as before.
                user_id=customer.id if customer else staff.id, restaurant_id=restaurant.id, order_number=orders._next_order_number(restaurant.id),
                order_type=OrderType.COUNTER, status=OrderStatus.PENDING,
                subtotal=Decimal("0.00"), tax=Decimal("0.00"), delivery_fee=Decimal("0.00"), discount=Decimal("0.00"), total=Decimal("0.00"),
                customer_name=f"{customer.first_name} {customer.last_name}".strip() if customer else f"{staff.first_name} (staff)",
                customer_email=customer.email if customer else None,
                notes=data.notes, client_token=secrets.token_urlsafe(16),
            )
            orders.orders.add(order)
            subtotal = orders._add_lines(order, data.items, items_by_id)
            coupon = None
            if data.coupon_code:
                if not FeatureService(self.db).is_enabled(restaurant.id, "coupons"):
                    raise AppError("Discount codes are not available for this restaurant")
                coupon, order.discount = orders.coupons.apply_to_order(restaurant.id, data.coupon_code, subtotal, customer)
            taxable = max(subtotal - order.discount, Decimal("0.00"))
            service_charge = service_charge_for(restaurant, OrderType.COUNTER, taxable)
            tax = price_order_tax(
                self.db, restaurant, order, discount=order.discount,
                taxable_service_charge=service_charge if restaurant.service_charge_taxable else Decimal("0.00"),
            ).tax_total
            total = (taxable + tax + service_charge).quantize(Decimal("0.01"))
            order.subtotal, order.tax, order.service_charge, order.total = subtotal, tax, service_charge, total
            if coupon is not None:
                orders.coupons.record_redemption(coupon, order, customer, order.discount)

            self.db.add(OrderStatusHistory(order_id=order.id, previous_status=None, new_status=OrderStatus.PENDING, changed_by_user_id=staff.id))
            # Stays PENDING, nothing published — see module docstring. mark_counter_order_paid_cash
            # is what actually confirms it, once it's actually paid.

        order_id, order_number, total = order.id, order.order_number, order.total
        self.db.commit()
        return PosOrderRead(order_id=order_id, order_number=order_number, total=total, status=OrderStatus.PENDING.value)

    # ------------------------------------------------------------------ customers, coupons, 86

    def _customer(self, restaurant_id: int, customer_id: int) -> User:
        customer = self.db.get(User, customer_id)
        if customer is None or customer.restaurant_id != restaurant_id:
            raise NotFoundError("Customer not found")
        return customer

    def search_customers(self, restaurant_id: int, query: str) -> list[PosCustomerRead]:
        """Registered customers of this restaurant by name, email or phone — for attaching to a sale."""
        q = query.strip()
        if len(q) < 2:
            return []
        pattern = f"%{q}%"
        users = self.db.scalars(
            select(User).where(
                User.restaurant_id == restaurant_id, User.is_active.is_(True),
                or_(User.first_name.ilike(pattern), User.last_name.ilike(pattern), User.email.ilike(pattern), User.phone.ilike(pattern)),
            ).order_by(User.first_name).limit(10)
        ).all()
        balances = {
            a.user_id: a.balance for a in self.db.scalars(
                select(LoyaltyAccount).where(LoyaltyAccount.restaurant_id == restaurant_id, LoyaltyAccount.user_id.in_([u.id for u in users]))
            )
        } if users else {}
        return [
            PosCustomerRead(
                id=u.id, name=f"{u.first_name} {u.last_name}".strip(), email=u.email, phone=u.phone,
                points=balances.get(u.id, 0), is_vip=u.is_vip,
            )
            for u in users
        ]

    def preview_coupon(self, restaurant_id: int, data: PosCouponPreviewRequest) -> PosCouponPreviewRead:
        if not FeatureService(self.db).is_enabled(restaurant_id, "coupons"):
            raise AppError("Discount codes are not available for this restaurant")
        customer = self._customer(restaurant_id, data.customer_id) if data.customer_id else None
        coupon, discount = OrderService(self.db).coupons.preview(restaurant_id, data.code, data.subtotal, customer)
        return PosCouponPreviewRead(code=coupon.code, description=coupon.description, discount=discount)

    def set_item_availability(self, staff: User, restaurant_id: int, item_id: int, is_available: bool) -> AvailabilityRead:
        """86 an item (or bring it back) from the till — takes effect on the web menu and every other device at once."""
        item = self.db.get(MenuItem, item_id)
        if item is None or item.restaurant_id != restaurant_id:
            raise NotFoundError("Menu item not found")
        if item.is_available != is_available:
            item.is_available = is_available
            self.db.add(AuditLog(
                restaurant_id=restaurant_id, actor_user_id=staff.id, actor_label=staff.email,
                action="pos.item_availability", target=f"menu_item:{item.id}", details={"is_available": is_available},
            ))
            self.db.commit()
        return AvailabilityRead(item_id=item.id, is_available=item.is_available)

    def mark_counter_order_paid_cash(self, restaurant_id: int, order_id: int, staff: User, device_id: int | None = None) -> None:
        order = self.db.get(Order, order_id)
        if order is None or order.restaurant_id != restaurant_id:
            raise NotFoundError("Order not found")
        if order.status != OrderStatus.PENDING:
            raise AppError("This order has already been paid")
        restaurant = self.db.get(Restaurant, restaurant_id)
        if restaurant is None:
            raise NotFoundError("Restaurant not found")
        payment = Payment(
            order_id=order.id, restaurant_id=restaurant_id, amount=order.total, currency=restaurant.currency,
            payment_method=PaymentMethod.CASH, provider="MANUAL",
            shift_id=ShiftService(self.db).current_shift_id(device_id), staff_user_id=staff.id,
        )
        self.db.add(payment)
        self.db.flush()
        OrderService(self.db).confirm_payment(order, payment, user_id=staff.id, notes="Cash tender at the POS")
        self.db.commit()

    def create_counter_order_card_intent(self, restaurant_id: int, order_id: int, staff: User, device_id: int | None = None) -> PosCardIntentRead:
        """Starts a card-present PaymentIntent for a counter order already created by
        create_counter_order. Unlike cash, a real (Stripe) payment is left PENDING here — the
        payment_intent.succeeded webhook's existing confirm_payment call is what actually confirms it,
        once the reader finishes. The mock provider still settles synchronously, exactly like
        OrderService.create_order already does, so this is fully testable without Stripe."""
        FeatureService(self.db).require(restaurant_id, FEATURE)  # reachable independently of order creation
        order = self.db.get(Order, order_id)
        if order is None or order.restaurant_id != restaurant_id:
            raise NotFoundError("Order not found")
        if order.status != OrderStatus.PENDING:
            raise AppError("This order has already been paid")
        restaurant = self.db.get(Restaurant, restaurant_id)
        if restaurant is None:
            raise NotFoundError("Restaurant not found")

        provider_name = settings.PAYMENT_PROVIDER.strip().upper()
        intent = get_payment_provider().create_intent(
            order.total, currency=restaurant.currency, connected_account_id=restaurant.stripe_account_id,
            metadata={"order_id": str(order.id), "restaurant_id": str(restaurant_id)}, card_present=True,
        )
        if intent.status == PaymentStatus.FAILED:
            raise AppError(intent.failure_message or "Payment failed")

        payment = Payment(
            order_id=order.id, restaurant_id=restaurant_id, amount=order.total, currency=restaurant.currency,
            status=intent.status, payment_method=PaymentMethod.CARD, provider=provider_name,
            provider_reference=intent.provider_intent_id, provider_intent_id=intent.provider_intent_id,
            shift_id=ShiftService(self.db).current_shift_id(device_id), staff_user_id=staff.id,
        )
        self.db.add(payment)
        self.db.flush()

        if intent.status == PaymentStatus.COMPLETED:
            # Mock provider settles synchronously — same reasoning as OrderService.create_order.
            OrderService(self.db).confirm_payment(order, payment, user_id=staff.id, notes="Card tender at the POS (mock)")
            self.db.commit()
            return PosCardIntentRead(order_id=order.id, status=OrderStatus.CONFIRMED.value)

        self.db.commit()
        return PosCardIntentRead(
            order_id=order.id, status=OrderStatus.PENDING.value,
            client_secret=intent.client_secret, provider_intent_id=intent.provider_intent_id,
        )
