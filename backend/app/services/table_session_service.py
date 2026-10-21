"""QR table ordering: scanning a table's code, joining its shared tab, ordering in rounds, closing it."""

import secrets
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.exceptions import (
    AppError,
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
)
from app.core.realtime import (
    kitchen_topic,
    publish,
    publish_order_change,
    session_topic,
)
from app.core.security import create_guest_token
from app.models.enums import (
    OrderStatus,
    OrderType,
    PaymentMethod,
    PaymentStatus,
    TableStatus,
)
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.order_status_history import OrderStatusHistory
from app.models.payment import Payment
from app.models.restaurant import Restaurant
from app.models.restaurant_table import RestaurantTable
from app.models.service_request import BILL, DONE, KINDS, ServiceRequest
from app.models.service_request import OPEN as REQUEST_OPEN
from app.models.table_session import CLOSED, OPEN, SessionGuest, TableSession
from app.schemas.table_session import (
    JoinResponse,
    OpenSessionRead,
    QrTableRead,
    RestaurantTableRead,
    RoundCreate,
    ServiceRequestStaffRead,
    SessionItemRead,
    SessionRead,
    SessionRoundRead,
    SplitRequest,
    TableInfo,
    TablePaymentRead,
    WaiterSessionRead,
    WaiterTableRead,
)
from app.services.feature_service import FeatureService
from app.services.order_service import OrderService
from app.services.payments import get_payment_provider, reverse_payment
from app.services.shift_service import ShiftService
from app.services.tax import (
    price_order_tax,
    record_paid_order,
    reverse_paid_order,
    service_charge_for,
)

FEATURE = "qr_table_ordering"
CLOSED_STATUSES = {OrderStatus.CANCELLED}


class TableSessionService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------ scanning

    def resolve_table(self, token: str, restaurant_id: int | None = None) -> tuple[RestaurantTable, Restaurant]:
        """The table behind a QR token. Unknown/rotated tokens, inactive tables and a mismatching site all look the
        same (404), so a token reveals nothing to someone who guesses."""
        table = self.db.scalar(select(RestaurantTable).where(RestaurantTable.qr_token == token))
        if table is None or not table.is_active or (restaurant_id is not None and table.restaurant_id != restaurant_id):
            raise NotFoundError("This QR code is not valid")
        restaurant = self.db.get(Restaurant, table.restaurant_id)
        if restaurant is None or not restaurant.is_active:
            raise NotFoundError("This QR code is not valid")
        FeatureService(self.db).require(restaurant.id, FEATURE)
        return table, restaurant

    def _restaurant(self, restaurant_id: int) -> Restaurant:
        restaurant = self.db.get(Restaurant, restaurant_id)
        if restaurant is None:
            raise NotFoundError("Restaurant not found")
        return restaurant

    def _closed_reason(self, table: RestaurantTable, restaurant: Restaurant) -> str | None:
        if restaurant.qr_access_policy == "OPEN" or table.status == TableStatus.OCCUPIED:
            return None
        return "Ordering opens once your host has seated you. Please ask a member of staff, then scan again."

    def info(self, token: str, restaurant_id: int | None = None) -> TableInfo:
        table, restaurant = self.resolve_table(token, restaurant_id)
        reason = self._closed_reason(table, restaurant)
        return TableInfo(
            restaurant_id=restaurant.id, restaurant_name=restaurant.name, table_number=table.table_number,
            ordering_open=reason is None, reason=reason,
        )

    def join(self, token: str, name: str | None, restaurant_id: int | None = None) -> JoinResponse:
        table, restaurant = self.resolve_table(token, restaurant_id)
        reason = self._closed_reason(table, restaurant)
        if reason is not None:
            raise ForbiddenError(reason)
        session = self._open_session(table)
        guest = SessionGuest(session_id=session.id, name=(name or "").strip() or None)
        self.db.add(guest)
        self.db.flush()
        self.db.commit()
        return JoinResponse(
            access_token=create_guest_token(guest.id, session.id, restaurant.id), session_id=session.id, guest_id=guest.id
        )

    def _open_session(self, table: RestaurantTable) -> TableSession:
        """The table's open session, created if this is the first scan. Two phones scanning at once end up in the same one."""
        existing = self.db.scalar(select(TableSession).where(TableSession.table_id == table.id, TableSession.state == OPEN))
        if existing is not None:
            return existing
        try:
            with self.db.begin_nested():
                session = TableSession(restaurant_id=table.restaurant_id, table_id=table.id)
                self.db.add(session)
                self.db.flush()
            publish(self.db, kitchen_topic(table.restaurant_id), "session.opened", {"table_id": table.id})
            return session
        except IntegrityError:  # someone else opened it between our read and our insert
            won_the_race = self.db.scalar(select(TableSession).where(TableSession.table_id == table.id, TableSession.state == OPEN))
            if won_the_race is None:
                raise  # truly shouldn't happen: the insert conflicted with a row that then isn't there
            return won_the_race

    def open_for_staff(self, table_id: int, restaurant_id: int, party_size: int | None, tab_name: str | None = None) -> OpenSessionRead:
        """Staff seat a walk-in directly from the POS — no QR scan involved. Gated on "pos", not
        qr_table_ordering, since this is a POS action independent of whether guest self-ordering is on.
        Idempotent like _open_session itself: tapping "Seat" on a table that already has a tab just
        returns it rather than erroring — the same "two people reach for the same table" tolerance the
        guest-QR path already has."""
        FeatureService(self.db).require(restaurant_id, "pos")
        table = self._table(table_id, restaurant_id)
        if not table.is_active:
            raise AppError("That table is out of service")
        session = self._open_session(table)
        if table.status != TableStatus.OCCUPIED:
            table.status = TableStatus.OCCUPIED  # mirrors what transfer() already does for its target table
        if party_size is not None and session.party_size is None:
            session.party_size = party_size
        if tab_name and tab_name.strip() and not session.tab_name:
            session.tab_name = tab_name.strip()
        self.db.commit()
        return self._open_session_read(session)

    # ------------------------------------------------------------------ the guest's view

    def authenticate(self, guest_id: int, session_id: int, restaurant_id: int) -> tuple[SessionGuest, TableSession]:
        guest = self.db.get(SessionGuest, guest_id)
        session = self.db.get(TableSession, session_id)
        if guest is None or session is None or guest.session_id != session.id or session.restaurant_id != restaurant_id:
            raise UnauthorizedError("Invalid table pass")
        if session.state != OPEN:
            raise UnauthorizedError("This table session has ended")
        return guest, session

    # ------------------------------------------------------------------ what's owed (split payments)

    def _paid(self, session_id: int) -> Decimal:
        return Decimal(self.db.scalar(select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.table_session_id == session_id, Payment.status == PaymentStatus.COMPLETED)) or 0)

    def _balance(self, session: TableSession) -> Decimal:
        total = Decimal(self.db.scalar(select(func.coalesce(func.sum(Order.total), 0)).where(
            Order.table_session_id == session.id, Order.status.notin_(CLOSED_STATUSES))) or 0)
        return max(total - self._paid(session.id), Decimal("0.00"))

    @staticmethod
    def _amount_due(item: OrderItem, order: Order) -> Decimal:
        """What paying for just this line costs: the line, its tax, and its share of the round's service charge."""
        share = (order.service_charge * item.line_total / order.subtotal) if order.subtotal > 0 else Decimal(0)
        return (item.line_total + item.tax_amount + share).quantize(Decimal("0.01"))

    def _split_amount(self, session: TableSession, split: SplitRequest | None) -> tuple[Decimal, list[OrderItem]]:
        """The amount one payment covers (never more than is owed) and, for "just these items", the lines it pays for."""
        balance = self._balance(session)
        if balance <= 0:
            raise AppError("There is nothing left to pay on this tab")
        split = split or SplitRequest()
        items: list[OrderItem] = []
        if split.mode == "FULL":
            amount = balance
        elif split.mode == "EVEN":
            parts = split.parts_remaining or 1
            amount = balance if parts <= 1 else (balance / parts).quantize(Decimal("0.01"))
        elif split.mode == "AMOUNT":
            if split.amount is None:
                raise AppError("Enter an amount")
            amount = split.amount.quantize(Decimal("0.01"))
        else:
            if not split.item_ids:
                raise AppError("Choose at least one item")
            items = list(self.db.scalars(
                select(OrderItem).join(Order, Order.id == OrderItem.order_id).options(selectinload(OrderItem.order)).where(
                    Order.table_session_id == session.id, Order.status.notin_(CLOSED_STATUSES), OrderItem.id.in_(split.item_ids),
                )
            ))
            if len(items) != len(set(split.item_ids)):
                raise AppError("One of those items isn't on this tab")
            if any(i.paid_payment_id is not None for i in items):
                raise AppError("One of those items has already been paid for")
            amount = min(sum((self._amount_due(i, i.order) for i in items), Decimal("0.00")), balance)
        if amount < Decimal("0.01"):
            raise AppError("That is too small an amount to take")
        if amount > balance:
            raise AppError(f"That is more than the {balance} still owed")
        return amount, items

    def _settle_session(self, session: TableSession, restaurant_id: int, staff_user_id: int | None) -> bool:
        """After a payment lands: close the tab if nothing is left owing, otherwise leave it open for the next part."""
        self.db.flush()
        if self._balance(session) <= 0:
            self.close_session(session.id, restaurant_id, staff_user_id)  # commits
            return True
        self.db.commit()
        return False

    def view(self, session: TableSession) -> SessionRead:
        table = session.table
        restaurant = self._restaurant(session.restaurant_id)
        orders = list(self.db.scalars(
            select(Order).options(selectinload(Order.items).selectinload(OrderItem.modifiers))
            .where(Order.table_session_id == session.id).order_by(Order.round_no, Order.id)
        ).all())
        names = {g.id: g.name for g in self.db.scalars(select(SessionGuest).where(SessionGuest.session_id == session.id))}
        rounds = [
            SessionRoundRead(
                order_id=o.id, order_number=o.order_number, round_no=o.round_no, status=o.status.value, total=o.total,
                ordered_by=names.get(o.session_guest_id) if o.session_guest_id else "Staff", created_at=o.created_at,
                items=[
                    SessionItemRead(
                        item_id=i.id, name=i.item_name, quantity=i.quantity, line_total=i.line_total, discount_amount=i.discount_amount,
                        course=i.course, held=i.held, paid=i.paid_payment_id is not None, amount_due=self._amount_due(i, o),
                        special_instructions=i.special_instructions, options=[m.option_name for m in i.modifiers],
                    ) for i in o.items
                ],
            ) for o in orders
        ]
        total = sum((o.total for o in orders if o.status not in CLOSED_STATUSES), Decimal("0.00"))
        paid = self._paid(session.id)
        requests = list(self.db.scalars(select(ServiceRequest.kind).where(
            ServiceRequest.table_session_id == session.id, ServiceRequest.state == REQUEST_OPEN).order_by(ServiceRequest.id)))
        return SessionRead(
            session_id=session.id, restaurant_id=session.restaurant_id, restaurant_name=restaurant.name,
            table_number=table.table_number, guests=[n for n in names.values() if n], rounds=rounds, total=total,
            paid=paid, balance=max(total - paid, Decimal("0.00")), tab_name=session.tab_name,
            requests=requests, stripe_account_id=restaurant.stripe_account_id,
            stripe_charges_enabled=restaurant.stripe_charges_enabled,
        )

    # ------------------------------------------------------------------ ordering

    def place_round(
        self, guest: SessionGuest | None, session: TableSession, data: RoundCreate, client_token: str | None,
        *, staff_user=None,
    ) -> SessionRoundRead:
        """A round from a guest's phone, or (with `staff_user`) one a waiter sends on the table's behalf."""
        if staff_user is None and guest is None:
            raise AppError("A round needs either a guest or a member of staff sending it")
        restaurant = self._restaurant(session.restaurant_id)
        FeatureService(self.db).require(restaurant.id, FEATURE)

        # Serialise rounds of one table so round numbers never repeat.
        self.db.execute(select(TableSession.id).where(TableSession.id == session.id).with_for_update())
        # After the lock, so two simultaneous taps of one button can't both get past this check.
        if client_token:  # a repeated tap or a retry after a dropped connection returns the original round
            again = self.db.scalar(select(Order).where(Order.table_session_id == session.id, Order.client_token == client_token))
            if again is not None:
                return self._round_read(again.id, session)

        round_no = (self.db.scalar(select(func.max(Order.round_no)).where(Order.table_session_id == session.id)) or 0) + 1

        # All-or-nothing: a refused round (sold out, too large…) leaves no order, no lines and no used order number.
        with self.db.begin_nested():
            orders = OrderService(self.db)
            item_ids = [line.menu_item_id for line in data.items]
            menu_items = orders.menu.get_items_by_ids(item_ids, restaurant.id)
            items_by_id = {item.id: item for item in menu_items}
            if len(items_by_id) != len(set(item_ids)):
                raise AppError("One or more menu items are invalid for this restaurant")

            if staff_user is not None:
                guest_name = f"{staff_user.first_name} (staff)"
            else:
                assert guest is not None  # guaranteed by the guard above
                guest_name = guest.name or f"Table {session.table.table_number}"
            order = Order(
                user_id=staff_user.id if staff_user else None, restaurant_id=restaurant.id, order_number=orders._next_order_number(restaurant.id),
                order_type=OrderType.DINE_IN, status=OrderStatus.PENDING,
                subtotal=Decimal("0.00"), tax=Decimal("0.00"), delivery_fee=Decimal("0.00"), discount=Decimal("0.00"), total=Decimal("0.00"),
                customer_name=guest_name, customer_email=None, table_id=session.table_id,
                table_session_id=session.id, session_guest_id=guest.id if guest else None, round_no=round_no,
                client_token=client_token, notes=data.notes,
            )
            orders.orders.add(order)
            subtotal = orders._add_lines(order, data.items, items_by_id, honor_courses=staff_user is not None)
            service_charge = service_charge_for(restaurant, OrderType.DINE_IN, subtotal)
            tax = price_order_tax(
                self.db, restaurant, order, taxable_service_charge=service_charge if restaurant.service_charge_taxable else Decimal("0.00"),
            ).tax_total
            total = (subtotal + tax + service_charge).quantize(Decimal("0.01"))
            if total > Decimal(str(settings.QR_MAX_ORDER_TOTAL)):
                raise AppError("That round is too large to send from a table. Please ask a member of staff.")
            order.subtotal, order.tax, order.service_charge, order.total = subtotal, tax, service_charge, total

            self.db.add(OrderStatusHistory(order_id=order.id, previous_status=None, new_status=OrderStatus.PENDING, changed_by_user_id=staff_user.id if staff_user else None))
            order.status = OrderStatus.CONFIRMED  # paid at the end of the meal, so nothing to wait for
            self.db.add(OrderStatusHistory(
                order_id=order.id, previous_status=OrderStatus.PENDING, new_status=OrderStatus.CONFIRMED,
                changed_by_user_id=staff_user.id if staff_user else None,
                notes=f"Sent by staff for table {session.table.table_number} (round {round_no})" if staff_user else f"Sent from table {session.table.table_number} (round {round_no})",
            ))

        order_id = order.id
        publish(self.db, kitchen_topic(restaurant.id), "order.created", {"order_id": order_id, "order_number": order.order_number})
        publish_order_change(self.db, order, "round.created", {"round_no": round_no})
        self.db.commit()
        return self._round_read(order_id, session)

    def _round_read(self, order_id: int, session: TableSession) -> SessionRoundRead:
        return next(r for r in self.view(session).rounds if r.order_id == order_id)

    # ------------------------------------------------------------------ staff

    def qr_tables(self, restaurant_id: int) -> list[QrTableRead]:
        tables = list(self.db.scalars(
            select(RestaurantTable).where(RestaurantTable.restaurant_id == restaurant_id, RestaurantTable.is_active.is_(True))
            .order_by(RestaurantTable.table_number)
        ).all())
        open_ids = set(self.db.scalars(select(TableSession.table_id).where(TableSession.restaurant_id == restaurant_id, TableSession.state == OPEN)))
        for table in tables:
            if not table.qr_token:  # tables made before QR ordering existed
                table.qr_token = secrets.token_urlsafe(16)
        self.db.commit()
        return [
            QrTableRead(table_id=t.id, table_number=t.table_number, zone=t.zone, qr_token=t.qr_token or "", has_open_session=t.id in open_ids)
            for t in tables
        ]

    def rotate_token(self, table_id: int, restaurant_id: int) -> QrTableRead:
        table = self._table(table_id, restaurant_id)
        table.qr_token = secrets.token_urlsafe(16)
        self.db.commit()
        has_open = self.db.scalar(select(TableSession.id).where(TableSession.table_id == table.id, TableSession.state == OPEN)) is not None
        return QrTableRead(table_id=table.id, table_number=table.table_number, zone=table.zone, qr_token=table.qr_token, has_open_session=has_open)

    def open_sessions(self, restaurant_id: int) -> list[OpenSessionRead]:
        sessions = list(self.db.scalars(
            select(TableSession).options(selectinload(TableSession.table))
            .where(TableSession.restaurant_id == restaurant_id, TableSession.state == OPEN).order_by(TableSession.opened_at)
        ).all())
        return [self._open_session_read(s) for s in sessions]

    def _open_session_read(self, s: TableSession) -> OpenSessionRead:
        guest_rows = self.db.scalar(select(func.count()).select_from(SessionGuest).where(SessionGuest.session_id == s.id)) or 0
        # party_size is only set when staff seated a walk-in (open_for_staff) — no one scanned, so
        # there's no SessionGuest row to count. The guest-QR path never sets party_size, so this
        # falls straight back to the live SessionGuest count exactly as before.
        guests = s.party_size if s.party_size is not None else guest_rows
        rounds = self.db.execute(select(func.count(), func.coalesce(func.sum(Order.total), 0)).where(
            Order.table_session_id == s.id, Order.status.notin_(CLOSED_STATUSES))).one()
        asked = list(self.db.scalars(select(ServiceRequest.kind).where(
            ServiceRequest.table_session_id == s.id, ServiceRequest.state == REQUEST_OPEN).order_by(ServiceRequest.id)))
        return OpenSessionRead(
            session_id=s.id, table_id=s.table_id, table_number=s.table.table_number, opened_at=s.opened_at,
            guests=guests, rounds=rounds[0], total=Decimal(rounds[1]), requests=asked, tab_name=s.tab_name,
            balance=max(Decimal(rounds[1]) - self._paid(s.id), Decimal("0.00")),
        )

    def close_session(self, session_id: int, restaurant_id: int, staff_user_id: int | None, *, paid: bool = True) -> None:
        """End the tab: every guest pass stops working, the table goes to cleaning and its QR code is replaced,
        so a photo of the old code is worthless."""
        session = self.db.get(TableSession, session_id)
        if session is None or session.restaurant_id != restaurant_id:
            raise NotFoundError("Session not found")
        if session.state != OPEN:
            raise AppError("This session is already closed")
        # The tab is settled: report each round to Stripe Tax (a no-op unless the restaurant uses it).
        if paid:  # a staff close with no payment (walk-out, comp) owes no tax record
            restaurant = self.db.get(Restaurant, restaurant_id)
            for paid_order in self.db.scalars(select(Order).where(Order.table_session_id == session.id, Order.status.notin_(CLOSED_STATUSES))):
                record_paid_order(self.db, restaurant, paid_order)
        session.state = CLOSED
        session.closed_at = datetime.now(UTC)
        session.closed_by_user_id = staff_user_id
        self._resolve_open_requests(session.id, staff_user_id)  # nobody is waiting for a table that has left
        table = session.table
        table.status = TableStatus.CLEANING
        table.qr_token = secrets.token_urlsafe(16)
        publish(self.db, kitchen_topic(restaurant_id), "session.closed", {"table_id": table.id})
        publish(self.db, session_topic(session.id), "session.closed", {"table_id": table.id})
        self.db.commit()

    # ------------------------------------------------------------------ paying the tab

    def pay(self, session: TableSession) -> TablePaymentRead:
        """A guest pays the table's whole tab from their phone — the online-card path. `mark_paid_cash`
        is the staff-at-the-counter equivalent, with no Stripe involvement at all."""
        restaurant = self._restaurant(session.restaurant_id)
        FeatureService(self.db).require(restaurant.id, FEATURE)
        if session.state != OPEN:
            raise AppError("This table has already been closed")
        total = self._balance(session)
        if total <= Decimal("0.00"):
            raise AppError("There is nothing left to pay on your table's tab")
        in_flight = self.db.scalar(
            select(Payment.id).where(
                Payment.table_session_id == session.id,
                Payment.status.in_((PaymentStatus.PENDING, PaymentStatus.REQUIRES_ACTION)),
            )
        )
        if in_flight is not None:
            raise AppError("A payment is already in progress for this table. Please wait a moment.")

        provider_name = settings.PAYMENT_PROVIDER.strip().upper()
        payment_method = PaymentMethod.CARD if provider_name == "STRIPE" else PaymentMethod.MOCK
        intent = get_payment_provider().create_intent(
            total, currency=restaurant.currency, connected_account_id=restaurant.stripe_account_id,
            metadata={"table_session_id": str(session.id), "restaurant_id": str(restaurant.id)},
        )
        if intent.status == PaymentStatus.FAILED:
            raise AppError(intent.failure_message or "Payment failed")

        payment = Payment(
            table_session_id=session.id, order_id=None, restaurant_id=restaurant.id, amount=total,
            currency=restaurant.currency, status=intent.status, payment_method=payment_method,
            provider=provider_name, provider_reference=intent.provider_intent_id,
            provider_intent_id=intent.provider_intent_id,
        )
        self.db.add(payment)
        self.db.flush()

        if intent.status == PaymentStatus.COMPLETED:
            # The mock provider settles synchronously — same reasoning as OrderService.create_order.
            payment.status = PaymentStatus.COMPLETED
            closed = self._settle_session(session, session.restaurant_id, None)
            return TablePaymentRead(closed=closed, balance=self._balance(session), payment_id=payment.id)

        self.db.commit()
        return TablePaymentRead(client_secret=intent.client_secret, balance=self._balance(session), payment_id=payment.id)

    def pay_by_card_at_pos(
        self, session_id: int, restaurant_id: int, staff_user_id: int, device_id: int | None = None, split: SplitRequest | None = None,
        reader_id: str | None = None,
    ) -> TablePaymentRead:
        """The Terminal (card-reader) equivalent of `mark_paid_cash` — staff-initiated from the POS, not
        the guest's own phone. Unlike `mark_paid_cash` (which marks COMPLETED outright, no Stripe
        involvement), this creates a real PaymentIntent and must branch on whether it settled
        synchronously, exactly like `pay()` does — so it mirrors `pay()`'s body with `card_present=True`
        rather than `mark_paid_cash`'s always-COMPLETED shape."""
        session = self.staff_session(session_id, restaurant_id)  # 404s / refuses an already-closed one
        restaurant = self._restaurant(restaurant_id)
        total, paying_items = self._split_amount(session, split)
        in_flight = self.db.scalar(
            select(Payment.id).where(
                Payment.table_session_id == session.id,
                Payment.status.in_((PaymentStatus.PENDING, PaymentStatus.REQUIRES_ACTION)),
            )
        )
        if in_flight is not None:
            raise AppError("A payment is already in progress for this table. Please wait a moment.")

        provider_name = settings.PAYMENT_PROVIDER.strip().upper()
        intent = get_payment_provider().create_intent(
            total, currency=restaurant.currency, connected_account_id=restaurant.stripe_account_id,
            metadata={"table_session_id": str(session.id), "restaurant_id": str(restaurant_id)},
            card_present=True,
        )
        if intent.status == PaymentStatus.FAILED:
            raise AppError(intent.failure_message or "Payment failed")

        payment = Payment(
            table_session_id=session.id, order_id=None, restaurant_id=restaurant_id, amount=total,
            currency=restaurant.currency, status=intent.status, payment_method=PaymentMethod.CARD,
            provider=provider_name, provider_reference=intent.provider_intent_id,
            provider_intent_id=intent.provider_intent_id,
            shift_id=ShiftService(self.db).current_shift_id(device_id),
            staff_user_id=staff_user_id,
        )
        self.db.add(payment)
        self.db.flush()
        for paid_item in paying_items:
            paid_item.paid_payment_id = payment.id

        if intent.status == PaymentStatus.COMPLETED:
            # The mock provider settles synchronously — same reasoning as pay()/OrderService.create_order.
            payment.status = PaymentStatus.COMPLETED
            closed = self._settle_session(session, restaurant_id, staff_user_id)
            return TablePaymentRead(closed=closed, balance=self._balance(session), payment_id=payment.id)

        if reader_id and intent.provider_intent_id:
            sent = get_payment_provider().process_on_reader(
                provider_intent_id=intent.provider_intent_id, reader_id=reader_id, connected_account_id=restaurant.stripe_account_id,
            )
            if not sent.success:
                get_payment_provider().cancel_intent(provider_intent_id=intent.provider_intent_id, connected_account_id=restaurant.stripe_account_id)
                payment.status = PaymentStatus.FAILED
                payment.failure_message = sent.message
                self.db.execute(update(OrderItem).where(OrderItem.paid_payment_id == payment.id).values(paid_payment_id=None))
                self.db.commit()
                raise AppError(sent.message or "The card reader didn't respond — check it's on and connected")
        self.db.commit()
        return TablePaymentRead(
            client_secret=None if reader_id else intent.client_secret, balance=self._balance(session), payment_id=payment.id,
        )

    def confirm_session_payment(self, payment: Payment) -> None:
        """Called from the payment_intent.succeeded webhook once a real (Stripe) session payment lands —
        the session-payment equivalent of OrderService.confirm_payment."""
        session = self.db.get(TableSession, payment.table_session_id)
        if session is None or session.state != OPEN:
            return  # already settled by an earlier delivery of this same event — nothing to do
        payment.status = PaymentStatus.COMPLETED
        self._settle_session(session, session.restaurant_id, payment.staff_user_id)

    def mark_paid_cash(
        self, session_id: int, restaurant_id: int, staff_user_id: int | None, device_id: int | None = None, split: SplitRequest | None = None,
    ) -> bool:
        """Staff records the tab as paid at the counter (cash, or a card on their own terminal) — no
        Stripe involvement. Closes the session the same way an online payment does. `device_id` is None
        for the non-POS (waiter/admin) caller — only a POS-initiated tender has a till shift to stamp."""
        session = self.staff_session(session_id, restaurant_id)  # 404s / refuses an already-closed one
        total, paying_items = self._split_amount(session, split)
        restaurant = self._restaurant(restaurant_id)
        payment = Payment(
            table_session_id=session.id, order_id=None, restaurant_id=restaurant_id, amount=total,
            currency=restaurant.currency, status=PaymentStatus.COMPLETED, payment_method=PaymentMethod.CASH,
            provider="MANUAL", shift_id=ShiftService(self.db).current_shift_id(device_id),
            staff_user_id=staff_user_id,
        )
        self.db.add(payment)
        self.db.flush()
        for paid_item in paying_items:
            paid_item.paid_payment_id = payment.id
        return self._settle_session(session, restaurant_id, staff_user_id)

    def refund_tab(self, session_id: int, restaurant_id: int, staff_user_id: int | None) -> None:
        """Refund a closed tab's payment in full (online card or cash — either way). API-level only for
        now: there's no admin page listing past sessions to reach this from yet, so it's reachable by id
        but not wired into any UI. Unlike OrderService.refund_payment (best-effort, never blocks a
        cancel), this is its own explicit action, so a provider failure is raised, not swallowed."""
        session = self.db.get(TableSession, session_id)
        if session is None or session.restaurant_id != restaurant_id:
            raise NotFoundError("Session not found")
        if session.state != CLOSED:
            raise AppError("Only a closed tab can be refunded")
        payments = list(self.db.scalars(
            select(Payment).where(Payment.table_session_id == session.id, Payment.status == PaymentStatus.COMPLETED).order_by(Payment.id)
        ))
        if not payments:
            raise AppError("There is no completed payment on this tab to refund")
        restaurant = self.db.get(Restaurant, restaurant_id)
        for payment in payments:  # a split tab has several; the whole tab comes back
            result = reverse_payment(payment, connected_account_id=restaurant.stripe_account_id if restaurant else None)
            if not result.success:
                raise AppError(result.message or "Refund failed")
        for refunded_order in self.db.scalars(select(Order).where(Order.table_session_id == session.id, Order.status.notin_(CLOSED_STATUSES))):
            reverse_paid_order(self.db, restaurant, refunded_order)
        self.db.commit()

    # ------------------------------------------------------------------ calling the waiter / asking for the bill

    def ask(self, guest: SessionGuest, session: TableSession, kind: str) -> list[str]:
        """A guest asks for the waiter or the bill. Asking again while it is still open changes nothing."""
        if kind not in KINDS:
            raise AppError("Unknown request")
        FeatureService(self.db).require(session.restaurant_id, FEATURE)
        if kind == BILL and not self.db.scalar(select(Order.id).where(Order.table_session_id == session.id).limit(1)):
            raise AppError("There is nothing on your table's tab yet")
        already = self.db.scalar(select(ServiceRequest.id).where(
            ServiceRequest.table_session_id == session.id, ServiceRequest.kind == kind, ServiceRequest.state == REQUEST_OPEN))
        if already is None:
            try:
                with self.db.begin_nested():
                    self.db.add(ServiceRequest(
                        restaurant_id=session.restaurant_id, table_session_id=session.id, table_id=session.table_id,
                        guest_id=guest.id, kind=kind))
                    self.db.flush()
            except IntegrityError:  # another phone at the table asked at the same moment
                already = True
            if already is None:
                data = {"table_id": session.table_id, "kind": kind}
                publish(self.db, kitchen_topic(session.restaurant_id), "request.created", data)
                publish(self.db, session_topic(session.id), "request.created", data)
        self.db.commit()
        return self.view(session).requests

    def open_requests(self, restaurant_id: int) -> list[ServiceRequestStaffRead]:
        rows = self.db.execute(
            select(ServiceRequest, RestaurantTable.table_number, SessionGuest.name)
            .join(RestaurantTable, RestaurantTable.id == ServiceRequest.table_id)
            .outerjoin(SessionGuest, SessionGuest.id == ServiceRequest.guest_id)
            .where(ServiceRequest.restaurant_id == restaurant_id, ServiceRequest.state == REQUEST_OPEN)
            .order_by(ServiceRequest.created_at, ServiceRequest.id)
        ).all()
        return [
            ServiceRequestStaffRead(id=r.id, session_id=r.table_session_id, table_id=r.table_id, table_number=number, kind=r.kind, asked_by=name, created_at=r.created_at)
            for r, number, name in rows
        ]

    def resolve_request(self, request_id: int, restaurant_id: int, staff_user_id: int | None) -> None:
        request = self.db.get(ServiceRequest, request_id)
        if request is None or request.restaurant_id != restaurant_id:
            raise NotFoundError("Request not found")
        if request.state == DONE:
            return  # two waiters tapped Done: fine
        request.state, request.resolved_at, request.resolved_by_user_id = DONE, datetime.now(UTC), staff_user_id
        data = {"table_id": request.table_id, "kind": request.kind}
        publish(self.db, kitchen_topic(restaurant_id), "request.done", data)
        publish(self.db, session_topic(request.table_session_id), "request.done", data)
        self.db.commit()

    def _resolve_open_requests(self, session_id: int, staff_user_id: int | None) -> None:
        self.db.execute(
            update(ServiceRequest)
            .where(ServiceRequest.table_session_id == session_id, ServiceRequest.state == REQUEST_OPEN)
            .values(state=DONE, resolved_at=datetime.now(UTC), resolved_by_user_id=staff_user_id)
        )

    # ------------------------------------------------------------------ waiter view

    def waiter_floor(self, restaurant_id: int) -> list[WaiterTableRead]:
        """Every active table with its live tab (if any): what a waiter needs on one screen."""
        tables = list(self.db.scalars(
            select(RestaurantTable).where(RestaurantTable.restaurant_id == restaurant_id, RestaurantTable.is_active.is_(True))
            .order_by(RestaurantTable.table_number)
        ).all())
        sessions = {s.table_id: s for s in self.open_sessions(restaurant_id)}
        ready: dict[int, int] = dict(self.db.execute(
            select(Order.table_session_id, func.count()).where(
                Order.restaurant_id == restaurant_id, Order.table_session_id.is_not(None), Order.status == OrderStatus.READY)
            .group_by(Order.table_session_id)
        ).all())  # type: ignore[arg-type]  # table_session_id is never None here (filtered above); mypy can't see it
        waiting: dict[int, datetime] = dict(self.db.execute(
            select(ServiceRequest.table_session_id, func.min(ServiceRequest.created_at)).where(
                ServiceRequest.restaurant_id == restaurant_id, ServiceRequest.state == REQUEST_OPEN)
            .group_by(ServiceRequest.table_session_id)
        ).all())  # type: ignore[arg-type]  # SQLAlchemy's Row isn't a plain tuple as far as mypy's dict() overload is concerned
        out = []
        for t in tables:
            s = sessions.get(t.id)
            out.append(WaiterTableRead(
                table_id=t.id, table_number=t.table_number, capacity=t.capacity, zone=t.zone, shape=t.shape,
                pos_x=t.pos_x, pos_y=t.pos_y, status=t.status.value,
                session=WaiterSessionRead(
                    session_id=s.session_id, opened_at=s.opened_at, guests=s.guests, rounds=s.rounds,
                    ready_rounds=ready.get(s.session_id, 0), total=s.total, requests=s.requests,
                    waiting_since=waiting.get(s.session_id),
                ) if s else None,
            ))
        return out

    def staff_session(self, session_id: int, restaurant_id: int) -> TableSession:
        session = self.db.get(TableSession, session_id)
        if session is None or session.restaurant_id != restaurant_id:
            raise NotFoundError("Session not found")
        if session.state != OPEN:
            raise AppError("This session is already closed")
        return session

    def transfer(self, session_id: int, restaurant_id: int, new_table_id: int) -> None:
        """Move a party's tab to another table: the tab keeps its rounds, the kitchen sees the new table number, the
        old table is left to be cleaned and its QR code is replaced."""
        session = self.staff_session(session_id, restaurant_id)
        target = self._table(new_table_id, restaurant_id)
        if target.id == session.table_id:
            raise AppError("That is already this table")
        if not target.is_active:
            raise AppError("That table is out of service")
        if self.db.scalar(select(TableSession.id).where(TableSession.table_id == target.id, TableSession.state == OPEN)) is not None:
            raise AppError("That table already has an open tab")
        old = session.table
        session.table_id = target.id
        self.db.execute(update(Order).where(Order.table_session_id == session.id).values(table_id=target.id))
        self.db.execute(update(ServiceRequest).where(ServiceRequest.table_session_id == session.id).values(table_id=target.id))
        old.status = TableStatus.CLEANING
        old.qr_token = secrets.token_urlsafe(16)
        target.status = TableStatus.OCCUPIED
        data = {"from_table_id": old.id, "table_id": target.id}
        publish(self.db, kitchen_topic(restaurant_id), "session.transferred", data)
        publish(self.db, session_topic(session.id), "session.transferred", data)
        self.db.commit()

    def merge(self, session_id: int, into_session_id: int, restaurant_id: int) -> None:
        """Fold one open tab into another (two parties joined up): every round, guest and open request moves across and
        the emptied tab is closed. Neither may have been part-paid — mixing half-settled bills isn't worth the risk."""
        if session_id == into_session_id:
            raise AppError("Pick a different tab to merge into")
        source = self.staff_session(session_id, restaurant_id)
        target = self.staff_session(into_session_id, restaurant_id)
        for s in (source, target):
            if self.db.scalar(select(Payment.id).where(
                Payment.table_session_id == s.id,
                Payment.status.in_((PaymentStatus.COMPLETED, PaymentStatus.PENDING, PaymentStatus.REQUIRES_ACTION)),
            ).limit(1)) is not None:
                raise AppError("A tab that is already being paid can't be merged")
        offset = self.db.scalar(select(func.coalesce(func.max(Order.round_no), 0)).where(Order.table_session_id == target.id)) or 0
        for order in self.db.scalars(select(Order).where(Order.table_session_id == source.id).order_by(Order.round_no, Order.id)):
            offset += 1
            order.table_session_id, order.table_id, order.round_no = target.id, target.table_id, offset
        self.db.execute(update(SessionGuest).where(SessionGuest.session_id == source.id).values(session_id=target.id))
        self.db.execute(update(ServiceRequest).where(ServiceRequest.table_session_id == source.id).values(table_session_id=target.id, table_id=target.table_id))
        if source.party_size:
            target.party_size = (target.party_size or 0) + source.party_size
        old_table = source.table
        source.state = CLOSED
        source.closed_at = datetime.now(UTC)
        old_table.status = TableStatus.CLEANING
        old_table.qr_token = secrets.token_urlsafe(16)
        data = {"merged_from": source.id, "into": target.id}
        publish(self.db, kitchen_topic(restaurant_id), "session.merged", data)
        publish(self.db, session_topic(target.id), "session.merged", data)
        publish(self.db, session_topic(source.id), "session.closed", {"table_id": old_table.id})
        self.db.commit()

    def fire_course(self, session_id: int, restaurant_id: int, course: int, staff_user_id: int | None) -> int:
        """Send a held course to the kitchen. Returns how many dishes were released."""
        session = self.staff_session(session_id, restaurant_id)
        items = list(self.db.scalars(
            select(OrderItem).join(Order, Order.id == OrderItem.order_id).where(
                Order.table_session_id == session.id, Order.status.notin_(CLOSED_STATUSES), OrderItem.held.is_(True), OrderItem.course <= course,
            )
        ))
        if not items:
            raise AppError("Nothing is being held for that course")
        order_ids = {i.order_id for i in items}
        for item in items:
            item.held = False
        for order in self.db.scalars(select(Order).where(Order.id.in_(order_ids))):
            if order.status == OrderStatus.READY:  # it was finished while this course was held back: there is cooking to do again
                self.db.add(OrderStatusHistory(order_id=order.id, previous_status=order.status, new_status=OrderStatus.PREPARING, changed_by_user_id=staff_user_id, notes=f"Course {course} fired"))
                order.status = OrderStatus.PREPARING
            publish(self.db, kitchen_topic(restaurant_id), "order.created", {"order_id": order.id, "order_number": order.order_number})
        self.db.commit()
        return len(items)

    def _table(self, table_id: int, restaurant_id: int) -> RestaurantTable:
        table = self.db.get(RestaurantTable, table_id)
        if table is None or table.restaurant_id != restaurant_id:
            raise NotFoundError("Table not found")
        return table

    def list_tables(self, restaurant_id: int) -> list[RestaurantTableRead]:
        """Every active table, for the POS's "pick a table to seat" view — status isn't used to decide
        seating eligibility (open_for_staff only cares whether a session is already OPEN for that table,
        same as the guest-QR path), so this stays a thin, permissive list rather than a floor-plan join."""
        tables = self.db.scalars(
            select(RestaurantTable).where(RestaurantTable.restaurant_id == restaurant_id, RestaurantTable.is_active.is_(True))
            .order_by(RestaurantTable.table_number)
        ).all()
        return [
            RestaurantTableRead(table_id=t.id, table_number=t.table_number, zone=t.zone, capacity=t.capacity)
            for t in tables
        ]
