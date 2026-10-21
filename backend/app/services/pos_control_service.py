"""POS controls: voids, comps, manual discounts and refunds, each with a reason, an audit trail, and — where the
signed-in person isn't allowed — a manager's PIN approval.

Voids/comps/discounts only touch an order nobody has paid for yet (a tab's rounds while the tab is open, or a
counter order before tender). Once money has been taken the only way back is a refund. Every change reprices
the order through the same tax seam used when it was placed, so tax and service charge stay right."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import AppError, ForbiddenError, NotFoundError
from app.core.pos_permissions import ACTIONS, REASONS, role_may
from app.core.realtime import kitchen_topic, publish, publish_order_change
from app.core.security import (
    OVERRIDE_MINUTES,
    create_override_token,
    decode_override_token,
    verify_password,
)
from app.dependencies.pos import PosStaff
from app.models.audit_log import AuditLog
from app.models.device import Device
from app.models.enums import OrderStatus, PaymentStatus
from app.models.order import Order
from app.models.order_adjustment import COMP, DISCOUNT, REFUND, VOID, OrderAdjustment
from app.models.order_item import OrderItem
from app.models.order_status_history import OrderStatusHistory
from app.models.payment import Payment
from app.models.restaurant import Restaurant
from app.models.restaurant_user import RestaurantUser
from app.models.table_session import CLOSED as SESSION_CLOSED
from app.models.table_session import OPEN as SESSION_OPEN
from app.models.table_session import TableSession
from app.models.user import User
from app.schemas.pos_control import (
    AdjustmentRead,
    AdjustmentResult,
    AuthorizeRead,
    DiscountRequest,
    ReasonRead,
    ReasonsRead,
    RecentPaymentRead,
)
from app.services.payments import reverse_payment
from app.services.shift_service import ShiftService
from app.services.tax import price_order_tax, reverse_paid_order, service_charge_for

FEATURE = "pos_controls"
CENT = Decimal("0.01")


class PosControlService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------ who may do what

    def reasons(self) -> ReasonsRead:
        return ReasonsRead(**{kind: [ReasonRead(code=c, label=l) for c, l in table.items()] for kind, table in REASONS.items()})

    def authorize(self, device: Device, pin: str, action: str) -> AuthorizeRead:
        """A manager types their own PIN to approve one action on this device."""
        if action not in ACTIONS:
            raise AppError("Unknown action")
        restaurant = self._restaurant(device.restaurant_id)
        members = self.db.scalars(select(RestaurantUser).where(
            RestaurantUser.restaurant_id == device.restaurant_id, RestaurantUser.is_active.is_(True), RestaurantUser.pin_hash.is_not(None),
        ))
        match = next((m for m in members if m.pin_hash and verify_password(pin, m.pin_hash)), None)
        user = self.db.get(User, match.user_id) if match else None
        if match is None or user is None or not user.is_active:
            raise AppError("Incorrect PIN")
        # Approval is for something the approver could do alone — a staff member can't approve a refund for a colleague.
        if not role_may(match.role, restaurant.pos_staff_permissions, action, percent=100.0 if action == "discount" else None):
            raise ForbiddenError("That PIN doesn't have permission to approve this")
        self.db.add(AuditLog(
            restaurant_id=device.restaurant_id, actor_user_id=user.id, actor_label=user.email,
            action="pos.override_granted", target=f"device:{device.id}", details={"action": action},
        ))
        self.db.commit()
        return AuthorizeRead(
            token=create_override_token(user.id, device.id, device.restaurant_id, action),
            approver=user.first_name, expires_in=OVERRIDE_MINUTES * 60,
        )

    def _approver(self, staff: PosStaff, action: str, override: str | None, percent: float | None = None) -> int | None:
        """The user who authorised this action when it wasn't the signed-in person's own call, else None.
        Raises a 403 the app reads as "ask a manager" when neither applies."""
        restaurant = self._restaurant(staff.device.restaurant_id)
        if role_may(staff.membership.role, restaurant.pos_staff_permissions, action, percent):
            return None
        if override:
            try:
                payload = decode_override_token(override)
            except ValueError as exc:
                raise ForbiddenError("Manager approval expired — ask again") from exc
            if payload.get("action") == action and int(payload["device"]) == staff.device.id and int(payload["tenant"]) == staff.device.restaurant_id:
                approver_id = int(payload["sub"])
                # A discount approval covers any percentage the approver could give themselves (admins: all).
                return approver_id
        raise ForbiddenError("Manager approval required")

    # ------------------------------------------------------------------ voids / comps / discounts

    def void_item(self, staff: PosStaff, item_id: int, quantity: int | None, reason: str, note: str | None, override: str | None) -> AdjustmentResult:
        item, order = self._editable_item(staff, item_id)
        qty = quantity or item.quantity
        if qty > item.quantity:
            raise AppError("You can't void more than was ordered")
        self._check_reason(VOID, reason, note)
        approver = self._approver(staff, "void", override)
        unit = (item.line_total / item.quantity).quantize(CENT)
        amount = item.line_total if qty == item.quantity else (unit * qty).quantize(CENT)
        snapshot = {"item": item.item_name, "quantity_voided": qty, "of": item.quantity, "sent_to_kitchen": order.status != OrderStatus.PENDING}
        adjustment = self._record(staff, VOID, order, amount, reason, note, approver, snapshot, item_id=item.id if qty < item.quantity else None)
        if qty == item.quantity:
            self.db.delete(item)
        else:
            item.quantity -= qty
            item.line_total = (item.line_total - amount).quantize(CENT)
        self.db.flush()
        self._reprice(order, staff, f"Voided {qty} × {item.item_name}")
        self.db.commit()
        return AdjustmentResult(adjustment_id=adjustment.id, amount=amount, order_total=order.total)

    def comp_item(self, staff: PosStaff, item_id: int, reason: str, note: str | None, override: str | None) -> AdjustmentResult:
        item, order = self._editable_item(staff, item_id)
        self._check_reason(COMP, reason, note)
        approver = self._approver(staff, "comp", override)
        amount = item.line_total
        if amount <= 0:
            raise AppError("That item is already free")
        adjustment = self._record(staff, COMP, order, amount, reason, note, approver, {"item": item.item_name, "quantity": item.quantity}, item_id=item.id)
        item.discount_amount += amount
        item.line_total = Decimal("0.00")
        self.db.flush()
        self._reprice(order, staff, f"Comped {item.item_name}")
        self.db.commit()
        return AdjustmentResult(adjustment_id=adjustment.id, amount=amount, order_total=order.total)

    def discount_item(self, staff: PosStaff, item_id: int, data: DiscountRequest, override: str | None) -> AdjustmentResult:
        item, order = self._editable_item(staff, item_id)
        return self._discount([item], order, staff, data, override, item_id=item.id)

    def discount_order(self, staff: PosStaff, order_id: int, data: DiscountRequest, override: str | None) -> AdjustmentResult:
        order = self._order(staff, order_id)
        self._ensure_editable(order)
        return self._discount(list(order.items), order, staff, data, override)

    def discount_session(self, staff: PosStaff, session_id: int, data: DiscountRequest, override: str | None) -> AdjustmentResult:
        session = self._open_session(staff, session_id)
        orders = list(self.db.scalars(
            select(Order).options(selectinload(Order.items)).where(Order.table_session_id == session.id, Order.status != OrderStatus.CANCELLED)
        ))
        items = [i for o in orders for i in o.items]
        if not items:
            raise AppError("There is nothing on this tab to discount")
        return self._discount(items, orders[0], staff, data, override, orders=orders, session_id=session.id)

    def _discount(
        self, items: list[OrderItem], order: Order, staff: PosStaff, data: DiscountRequest, override: str | None, *,
        item_id: int | None = None, orders: list[Order] | None = None, session_id: int | None = None,
    ) -> AdjustmentResult:
        self._check_reason(DISCOUNT, data.reason_code, data.note)
        base = sum((i.line_total for i in items), Decimal("0.00"))
        if base <= 0:
            raise AppError("There is nothing left to discount")
        amount = (base * data.percent / 100).quantize(CENT) if data.percent is not None else min(data.amount or Decimal(0), base)
        pct = float(amount / base * 100)
        approver = self._approver(staff, "discount", override, percent=pct)
        # Spread across the lines in proportion to what each costs, the last absorbing the rounding.
        remaining = amount
        for index, line in enumerate(items):
            share = remaining if index == len(items) - 1 else (amount * line.line_total / base).quantize(CENT)
            share = min(share, line.line_total)
            line.discount_amount += share
            line.line_total = (line.line_total - share).quantize(CENT)
            remaining -= share
        self.db.flush()
        touched = orders or [order]
        adjustment = self._record(
            staff, DISCOUNT, order, amount, data.reason_code, data.note, approver,
            {"percent": f"{pct:.2f}", "scope": "line" if item_id else ("tab" if session_id else "order")}, item_id=item_id, session_id=session_id,
        )
        for o in touched:
            self._reprice(o, staff, "Manual discount")
        self.db.commit()
        return AdjustmentResult(adjustment_id=adjustment.id, amount=amount, order_total=order.total)

    # ------------------------------------------------------------------ refunds

    def refund_order(self, staff: PosStaff, order_id: int, reason: str, note: str | None, override: str | None) -> AdjustmentResult:
        order = self._order(staff, order_id)
        if order.table_session_id is not None:
            raise AppError("This order belongs to a tab — refund the tab instead")
        payment = self.db.scalar(select(Payment).where(Payment.order_id == order.id, Payment.status == PaymentStatus.COMPLETED).order_by(Payment.id.desc()))
        if payment is None:
            raise AppError("There is no completed payment on this order to refund")
        return self._refund(staff, payment, order, None, reason, note, override)

    def refund_session(self, staff: PosStaff, session_id: int, reason: str, note: str | None, override: str | None) -> AdjustmentResult:
        session = self.db.get(TableSession, session_id)
        if session is None or session.restaurant_id != staff.device.restaurant_id:
            raise NotFoundError("Session not found")
        if session.state != SESSION_CLOSED:
            raise AppError("Only a settled tab can be refunded")
        payment = self.db.scalar(select(Payment).where(Payment.table_session_id == session.id, Payment.status == PaymentStatus.COMPLETED).order_by(Payment.id.desc()))
        if payment is None:
            raise AppError("There is no completed payment on this tab to refund")
        return self._refund(staff, payment, None, session, reason, note, override)

    def _refund(self, staff: PosStaff, payment: Payment, order: Order | None, session: TableSession | None, reason: str, note: str | None, override: str | None) -> AdjustmentResult:
        self._check_reason(REFUND, reason, note)
        approver = self._approver(staff, "refund", override)
        restaurant = self._restaurant(staff.device.restaurant_id)
        amount = payment.amount + payment.tip_amount
        result = reverse_payment(payment, connected_account_id=restaurant.stripe_account_id)
        if not result.success:
            raise AppError(result.message or "The refund was declined")
        if order is not None:
            orders = [order]
        else:
            assert session is not None
            orders = list(self.db.scalars(select(Order).where(Order.table_session_id == session.id)))
        for o in orders:
            reverse_paid_order(self.db, restaurant, o)
            if o.status != OrderStatus.CANCELLED:
                self.db.add(OrderStatusHistory(order_id=o.id, previous_status=o.status, new_status=OrderStatus.CANCELLED, changed_by_user_id=staff.user.id, notes=f"Refunded at the POS ({reason})"))
                o.status = OrderStatus.CANCELLED
        adjustment = OrderAdjustment(
            restaurant_id=restaurant.id, order_id=order.id if order else None, table_session_id=session.id if session else None,
            kind=REFUND, amount=amount, reason_code=reason, note=note, staff_user_id=staff.user.id, authorized_by_user_id=approver,
            shift_id=ShiftService(self.db).current_shift_id(staff.device.id), payment_method=payment.payment_method.value,
            original_shift_id=payment.shift_id, detail={"payment_id": payment.id},
        )
        self.db.add(adjustment)
        self._audit(staff, "pos.refund", f"payment:{payment.id}", {"amount": str(amount), "reason": reason, "approved_by": approver})
        self.db.commit()
        return AdjustmentResult(adjustment_id=adjustment.id, amount=amount)

    # ------------------------------------------------------------------ lists

    def recent_payments(self, staff: PosStaff, hours: int = 24) -> list[RecentPaymentRead]:
        from datetime import UTC, timedelta

        since = datetime.now(UTC) - timedelta(hours=hours)
        payments = self.db.scalars(
            select(Payment).where(
                Payment.restaurant_id == staff.device.restaurant_id, Payment.status == PaymentStatus.COMPLETED,
                Payment.staff_user_id.is_not(None), Payment.created_at >= since,
            ).order_by(Payment.id.desc()).limit(100)
        ).all()
        out: list[RecentPaymentRead] = []
        for p in payments:
            if p.order_id is not None:
                order = self.db.get(Order, p.order_id)
                label = f"Order {order.order_number}" if order else f"Order #{p.order_id}"
                kind, ident = "ORDER", p.order_id
            else:
                session = self.db.get(TableSession, p.table_session_id) if p.table_session_id else None
                label = f"Table {session.table.table_number}" if session else "Tab"
                kind, ident = "TAB", p.table_session_id or 0
            out.append(RecentPaymentRead(kind=kind, id=ident, label=label, amount=p.amount + p.tip_amount, method=p.payment_method.value, paid_at=p.created_at, refundable=True))
        return out

    def list_adjustments(self, restaurant_id: int, start: datetime, end: datetime) -> list[AdjustmentRead]:
        rows = self.db.execute(
            select(OrderAdjustment, Order.order_number).outerjoin(Order, Order.id == OrderAdjustment.order_id)
            .where(OrderAdjustment.restaurant_id == restaurant_id, OrderAdjustment.created_at >= start, OrderAdjustment.created_at <= end)
            .order_by(OrderAdjustment.id.desc()).limit(500)
        ).all()
        ids = {x for a, _ in rows for x in (a.staff_user_id, a.authorized_by_user_id) if x}
        names = {u.id: u.first_name for u in self.db.scalars(select(User).where(User.id.in_(ids)))} if ids else {}
        return [
            AdjustmentRead(
                id=a.id, kind=a.kind, amount=a.amount, reason_code=a.reason_code, note=a.note, order_number=number,
                staff=names.get(a.staff_user_id) if a.staff_user_id else None,
                authorized_by=names.get(a.authorized_by_user_id) if a.authorized_by_user_id else None,
                created_at=a.created_at, detail=a.detail,
            )
            for a, number in rows
        ]

    # ------------------------------------------------------------------ helpers

    def _restaurant(self, restaurant_id: int) -> Restaurant:
        restaurant = self.db.get(Restaurant, restaurant_id)
        if restaurant is None:
            raise NotFoundError("Restaurant not found")
        return restaurant

    def _order(self, staff: PosStaff, order_id: int) -> Order:
        order = self.db.scalar(select(Order).options(selectinload(Order.items)).where(Order.id == order_id))
        if order is None or order.restaurant_id != staff.device.restaurant_id:
            raise NotFoundError("Order not found")
        return order

    def _open_session(self, staff: PosStaff, session_id: int) -> TableSession:
        session = self.db.get(TableSession, session_id)
        if session is None or session.restaurant_id != staff.device.restaurant_id:
            raise NotFoundError("Session not found")
        if session.state != SESSION_OPEN:
            raise AppError("This tab is already settled")
        return session

    def _ensure_editable(self, order: Order) -> None:
        if order.table_session_id is not None:
            session = self.db.get(TableSession, order.table_session_id)
            if session is None or session.state != SESSION_OPEN:
                raise AppError("This tab is already settled — refund it instead")
        elif order.status != OrderStatus.PENDING:
            raise AppError("This order is already paid — refund it instead")
        if order.status == OrderStatus.CANCELLED:
            raise AppError("This order was cancelled")

    def _editable_item(self, staff: PosStaff, item_id: int) -> tuple[OrderItem, Order]:
        item = self.db.get(OrderItem, item_id)
        order = self._order(staff, item.order_id) if item is not None else None
        if item is None or order is None:
            raise NotFoundError("Item not found")
        self._ensure_editable(order)
        return item, order

    @staticmethod
    def _check_reason(kind: str, code: str, note: str | None) -> None:
        if code not in REASONS[kind]:
            raise AppError("Choose a reason from the list")
        if code == "OTHER" and len((note or "").strip()) < 3:
            raise AppError("Add a short note explaining the reason")

    def _record(
        self, staff: PosStaff, kind: str, order: Order, amount: Decimal, reason: str, note: str | None, approver: int | None,
        detail: dict, *, item_id: int | None = None, session_id: int | None = None,
    ) -> OrderAdjustment:
        adjustment = OrderAdjustment(
            restaurant_id=order.restaurant_id, order_id=order.id, table_session_id=session_id or order.table_session_id, order_item_id=item_id,
            kind=kind, amount=amount, reason_code=reason, note=(note or "").strip() or None, staff_user_id=staff.user.id,
            authorized_by_user_id=approver, shift_id=ShiftService(self.db).current_shift_id(staff.device.id), detail=detail,
        )
        self.db.add(adjustment)
        self.db.flush()
        self._audit(staff, f"pos.{kind.lower()}", f"order:{order.id}", {"amount": str(amount), "reason": reason, "approved_by": approver})
        return adjustment

    def _audit(self, staff: PosStaff, action: str, target: str, details: dict) -> None:
        self.db.add(AuditLog(
            restaurant_id=staff.device.restaurant_id, actor_user_id=staff.user.id, actor_label=staff.user.email,
            action=action, target=target, details=details,
        ))

    def _reprice(self, order: Order, staff: PosStaff, why: str) -> None:
        """Recompute subtotal / tax / service charge / total from the lines that remain, through the tax seam."""
        self.db.expire(order, ["items"])
        restaurant = self._restaurant(order.restaurant_id)
        items = list(order.items)
        if not items:
            self.db.add(OrderStatusHistory(order_id=order.id, previous_status=order.status, new_status=OrderStatus.CANCELLED, changed_by_user_id=staff.user.id, notes=why))
            order.status = OrderStatus.CANCELLED
            order.subtotal = order.tax = order.service_charge = order.total = Decimal("0.00")
            publish(self.db, kitchen_topic(order.restaurant_id), "order.cancelled", {"order_id": order.id})
            publish_order_change(self.db, order, "order.status")
            return
        subtotal = sum((i.line_total for i in items), Decimal("0.00"))
        discount = min(order.discount, subtotal)
        taxable = max(subtotal - discount, Decimal("0.00"))
        service_charge = service_charge_for(restaurant, order.order_type, taxable)
        tax = price_order_tax(
            self.db, restaurant, order, discount=discount, delivery_fee=order.delivery_fee,
            taxable_service_charge=service_charge if restaurant.service_charge_taxable else Decimal("0.00"),
        ).tax_total
        order.subtotal, order.service_charge, order.tax = subtotal, service_charge, tax
        order.total = (taxable + tax + order.delivery_fee + service_charge).quantize(CENT)
        if order.status != OrderStatus.PENDING:  # the kitchen has it: tell their screen the ticket changed
            publish(self.db, kitchen_topic(order.restaurant_id), "order.updated", {"order_id": order.id, "order_number": order.order_number})
            publish_order_change(self.db, order, "order.updated")
