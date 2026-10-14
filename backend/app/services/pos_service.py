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

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.core.security import (
    POS_SESSION_MINUTES,
    create_device_token,
    create_pos_session_token,
    hash_password,
    verify_password,
)
from app.models.audit_log import AuditLog
from app.models.device import Device
from app.models.enums import OrderStatus, OrderType, PaymentMethod
from app.models.order import Order
from app.models.order_status_history import OrderStatusHistory
from app.models.payment import Payment
from app.models.restaurant import Restaurant
from app.models.restaurant_user import RestaurantUser
from app.models.user import User
from app.schemas.pos import (
    DevicePairResponse,
    DeviceRead,
    PinLoginResponse,
    PosOrderCreate,
    PosOrderRead,
)
from app.services.feature_service import FeatureService
from app.services.order_service import OrderService

FEATURE = "pos"


class PosService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------ pairing (admin-facing)

    def pair_device(self, restaurant_id: int, label: str, admin: User) -> DevicePairResponse:
        device = Device(restaurant_id=restaurant_id, label=label, paired_by_user_id=admin.id)
        self.db.add(device)
        self.db.flush()
        self.db.add(AuditLog(restaurant_id=restaurant_id, actor_user_id=admin.id, actor_label=admin.email, action="device.paired", target=label))
        self.db.commit()
        token = create_device_token(device.id, restaurant_id)
        return DevicePairResponse(device_id=device.id, label=device.label, device_token=token)

    def list_devices(self, restaurant_id: int) -> list[DeviceRead]:
        devices = self.db.scalars(select(Device).where(Device.restaurant_id == restaurant_id).order_by(Device.created_at.desc())).all()
        return [
            DeviceRead(
                id=d.id, label=d.label, paired_by_label=d.paired_by.email if d.paired_by else None,
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
        return PinLoginResponse(pos_session_token=token, staff_name=user.first_name, expires_in=POS_SESSION_MINUTES * 60)

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

            order = Order(
                user_id=staff.id, restaurant_id=restaurant.id, order_number=orders._next_order_number(restaurant.id),
                order_type=OrderType.COUNTER, status=OrderStatus.PENDING,
                subtotal=Decimal("0.00"), tax=Decimal("0.00"), delivery_fee=Decimal("0.00"), discount=Decimal("0.00"), total=Decimal("0.00"),
                customer_name=f"{staff.first_name} (staff)", customer_email=None,
                notes=data.notes, client_token=secrets.token_urlsafe(16),
            )
            orders.orders.add(order)
            subtotal = orders._add_lines(order, data.items, items_by_id)
            tax = (subtotal * restaurant.tax_rate).quantize(Decimal("0.01"))
            total = (subtotal + tax).quantize(Decimal("0.01"))
            order.subtotal, order.tax, order.total = subtotal, tax, total

            self.db.add(OrderStatusHistory(order_id=order.id, previous_status=None, new_status=OrderStatus.PENDING, changed_by_user_id=staff.id))
            # Stays PENDING, nothing published — see module docstring. mark_counter_order_paid_cash
            # is what actually confirms it, once it's actually paid.

        order_id, order_number, total = order.id, order.order_number, order.total
        self.db.commit()
        return PosOrderRead(order_id=order_id, order_number=order_number, total=total, status=OrderStatus.PENDING.value)

    def mark_counter_order_paid_cash(self, restaurant_id: int, order_id: int, staff: User) -> None:
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
        )
        self.db.add(payment)
        self.db.flush()
        OrderService(self.db).confirm_payment(order, payment, user_id=staff.id, notes="Cash tender at the POS")
        self.db.commit()
