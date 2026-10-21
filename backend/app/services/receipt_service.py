"""Receipts and checks, built from what is stored: an order, or a whole table tab. One structure feeds the screen,
the printer bytes, AirPrint and the emailed copy, so they can never disagree."""

import base64
from datetime import UTC, datetime
from decimal import Decimal
from html import escape

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core import escpos
from app.core.exceptions import AppError, NotFoundError
from app.models.enums import OrderStatus, PaymentStatus
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.payment import Payment
from app.models.restaurant import Restaurant
from app.models.table_session import TableSession
from app.models.user import User
from app.schemas.receipt import EscPosRead, Receipt, ReceiptLine, ReceiptPayment
from app.services.notifications import _layout, _queue_email

ZERO = Decimal("0.00")


class ReceiptService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------ building

    def for_order(self, restaurant_id: int, order_id: int) -> Receipt:
        order = self.db.scalar(
            select(Order).options(selectinload(Order.items).selectinload(OrderItem.modifiers)).where(Order.id == order_id)
        )
        if order is None or order.restaurant_id != restaurant_id:
            raise NotFoundError("Order not found")
        payments = list(self.db.scalars(select(Payment).where(Payment.order_id == order.id).order_by(Payment.id)))
        return self._build(
            restaurant_id, kind="ORDER", reference=f"Order {order.order_number}", orders=[order], payments=payments,
            served_by=self._name(payments[0].staff_user_id) if payments else None,
        )

    def for_session(self, restaurant_id: int, session_id: int) -> Receipt:
        session = self.db.get(TableSession, session_id)
        if session is None or session.restaurant_id != restaurant_id:
            raise NotFoundError("Session not found")
        orders = list(self.db.scalars(
            select(Order).options(selectinload(Order.items).selectinload(OrderItem.modifiers))
            .where(Order.table_session_id == session.id, Order.status != OrderStatus.CANCELLED).order_by(Order.round_no, Order.id)
        ))
        payments = list(self.db.scalars(select(Payment).where(Payment.table_session_id == session.id).order_by(Payment.id)))
        label = f"Table {session.table.table_number}" + (f" · {session.tab_name}" if session.tab_name else "")
        return self._build(
            restaurant_id, kind="TAB", reference=label, orders=orders, payments=payments,
            served_by=self._name(payments[0].staff_user_id) if payments else None,
        )

    def _name(self, user_id: int | None) -> str | None:
        user = self.db.get(User, user_id) if user_id else None
        return user.first_name if user else None

    def _build(self, restaurant_id: int, *, kind: str, reference: str, orders: list[Order], payments: list[Payment], served_by: str | None) -> Receipt:
        restaurant = self.db.get(Restaurant, restaurant_id)
        if restaurant is None:
            raise NotFoundError("Restaurant not found")
        lines = [
            ReceiptLine(
                quantity=i.quantity, name=i.item_name, options=[m.option_name for m in i.modifiers],
                note=i.special_instructions, amount=i.line_total, discount=i.discount_amount,
            )
            for o in orders for i in o.items
        ]
        total = sum((o.total for o in orders), ZERO)
        done = [p for p in payments if p.status == PaymentStatus.COMPLETED]
        paid = sum((p.amount for p in done), ZERO)
        tip = sum((p.tip_amount for p in done), ZERO)
        address = [x for x in (restaurant.address, " ".join(p for p in (restaurant.city, restaurant.state, restaurant.postal_code) if p)) if x]
        return Receipt(
            restaurant_name=restaurant.name, address_lines=address, phone=restaurant.phone, kind=kind,
            title="Receipt" if paid >= total > 0 else ("Check" if kind == "TAB" else "Receipt"),
            reference=reference, served_by=served_by, printed_at=datetime.now(UTC), currency=restaurant.currency, lines=lines,
            subtotal=sum((o.subtotal for o in orders), ZERO), discount=sum((o.discount for o in orders), ZERO),
            service_charge=sum((o.service_charge for o in orders), ZERO), tax=sum((o.tax for o in orders), ZERO),
            delivery_fee=sum((o.delivery_fee for o in orders), ZERO), total=total, paid=paid, tip=tip,
            balance=max(total - paid, ZERO),
            payments=[ReceiptPayment(method=p.payment_method.value, amount=p.amount, tip=p.tip_amount, status=p.status.value) for p in payments],
        )

    # ------------------------------------------------------------------ outputs

    @staticmethod
    def escpos(receipt: Receipt, *, width: int = 42, drawer_kick: bool = False) -> EscPosRead:
        return EscPosRead(data=base64.b64encode(escpos.render(receipt, width=width, drawer_kick=drawer_kick)).decode(), drawer_kick=drawer_kick)

    def email(self, restaurant_id: int, receipt: Receipt, to: str, dedupe: str) -> None:
        restaurant = self.db.get(Restaurant, restaurant_id)
        if restaurant is None:
            raise NotFoundError("Restaurant not found")
        if receipt.balance > 0 and receipt.kind == "TAB":
            raise AppError("This tab hasn't been paid yet — there's no receipt to send")
        rows = "".join(
            f'<tr><td style="padding:4px 0">{line.quantity}× {escape(line.name)}'
            + "".join(f'<div style="color:#6b6f6c;font-size:12px">+ {escape(o)}</div>' for o in line.options)
            + f'</td><td align="right" style="padding:4px 0">${line.amount:.2f}</td></tr>'
            for line in receipt.lines
        )
        totals = [("Subtotal", receipt.subtotal)]
        if receipt.discount > 0:
            totals.append(("Discount", -receipt.discount))
        if receipt.service_charge > 0:
            totals.append(("Service charge", receipt.service_charge))
        if receipt.delivery_fee > 0:
            totals.append(("Delivery", receipt.delivery_fee))
        totals.append(("Tax", receipt.tax))
        if receipt.tip > 0:
            totals.append(("Tip", receipt.tip))
        total_rows = "".join(f'<tr><td>{label}</td><td align="right">{"-" if v < 0 else ""}${abs(v):.2f}</td></tr>' for label, v in totals)
        body = (
            f"<p>{escape(receipt.reference)} · {receipt.printed_at:%Y-%m-%d %H:%M}</p>"
            f'<table width="100%" cellpadding="0" cellspacing="0" style="font-size:14px">{rows}</table><hr style="border:0;border-top:1px solid #eee">'
            f'<table width="100%" cellpadding="0" cellspacing="0" style="font-size:14px">{total_rows}'
            f'<tr><td><strong>Total</strong></td><td align="right"><strong>${receipt.total:.2f}</strong></td></tr></table>'
        )
        text = "\n".join([f"{receipt.restaurant_name} — {receipt.reference}"] + [f"{l.quantity}x {l.name}  ${l.amount:.2f}" for l in receipt.lines] + [f"Total ${receipt.total:.2f}"])
        _queue_email(self.db, restaurant, to, f"Your receipt from {restaurant.name}", text, _layout(restaurant, "Your receipt", body), dedupe)
        self.db.commit()
