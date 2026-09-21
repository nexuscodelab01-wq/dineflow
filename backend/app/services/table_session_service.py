"""QR table ordering: scanning a table's code, joining its shared tab, ordering in rounds, closing it."""

import secrets
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.exceptions import AppError, ForbiddenError, NotFoundError, UnauthorizedError
from app.core.realtime import kitchen_topic, publish, publish_order_change, session_topic
from app.core.security import create_guest_token
from app.models.enums import OrderStatus, OrderType, TableStatus
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.order_status_history import OrderStatusHistory
from app.models.restaurant import Restaurant
from app.models.restaurant_table import RestaurantTable
from app.models.service_request import BILL, DONE, KINDS, ServiceRequest
from app.models.service_request import OPEN as REQUEST_OPEN
from app.models.table_session import CLOSED, OPEN, SessionGuest, TableSession
from app.schemas.table_session import (
    JoinResponse,
    OpenSessionRead,
    QrTableRead,
    RoundCreate,
    ServiceRequestStaffRead,
    SessionItemRead,
    SessionRead,
    SessionRoundRead,
    TableInfo,
    WaiterSessionRead,
    WaiterTableRead,
)
from app.services.feature_service import FeatureService
from app.services.order_service import OrderService

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
            return self.db.scalar(select(TableSession).where(TableSession.table_id == table.id, TableSession.state == OPEN))

    # ------------------------------------------------------------------ the guest's view

    def authenticate(self, guest_id: int, session_id: int, restaurant_id: int) -> tuple[SessionGuest, TableSession]:
        guest = self.db.get(SessionGuest, guest_id)
        session = self.db.get(TableSession, session_id)
        if guest is None or session is None or guest.session_id != session.id or session.restaurant_id != restaurant_id:
            raise UnauthorizedError("Invalid table pass")
        if session.state != OPEN:
            raise UnauthorizedError("This table session has ended")
        return guest, session

    def view(self, session: TableSession) -> SessionRead:
        table = session.table
        restaurant = self.db.get(Restaurant, session.restaurant_id)
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
                        name=i.item_name, quantity=i.quantity, line_total=i.line_total,
                        special_instructions=i.special_instructions, options=[m.option_name for m in i.modifiers],
                    ) for i in o.items
                ],
            ) for o in orders
        ]
        total = sum((o.total for o in orders if o.status not in CLOSED_STATUSES), Decimal("0.00"))
        requests = list(self.db.scalars(select(ServiceRequest.kind).where(
            ServiceRequest.table_session_id == session.id, ServiceRequest.state == REQUEST_OPEN).order_by(ServiceRequest.id)))
        return SessionRead(
            session_id=session.id, restaurant_id=session.restaurant_id, restaurant_name=restaurant.name,
            table_number=table.table_number, guests=[n for n in names.values() if n], rounds=rounds, total=total,
            requests=requests,
        )

    # ------------------------------------------------------------------ ordering

    def place_round(
        self, guest: SessionGuest | None, session: TableSession, data: RoundCreate, client_token: str | None,
        *, staff_user=None,
    ) -> SessionRoundRead:
        """A round from a guest's phone, or (with `staff_user`) one a waiter sends on the table's behalf."""
        restaurant = self.db.get(Restaurant, session.restaurant_id)
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

            guest_name = f"{staff_user.first_name} (staff)" if staff_user is not None else (guest.name or f"Table {session.table.table_number}")
            order = Order(
                user_id=None, restaurant_id=restaurant.id, order_number=orders._next_order_number(restaurant.id),
                order_type=OrderType.DINE_IN, status=OrderStatus.PENDING,
                subtotal=Decimal("0.00"), tax=Decimal("0.00"), delivery_fee=Decimal("0.00"), discount=Decimal("0.00"), total=Decimal("0.00"),
                customer_name=guest_name, customer_email=None, table_id=session.table_id,
                table_session_id=session.id, session_guest_id=guest.id if guest else None, round_no=round_no,
                client_token=client_token, notes=data.notes,
            )
            orders.orders.add(order)
            subtotal, _ = orders._add_lines(order, data.items, items_by_id)
            tax = (subtotal * restaurant.tax_rate).quantize(Decimal("0.01"))
            total = (subtotal + tax).quantize(Decimal("0.01"))
            if total > Decimal(str(settings.QR_MAX_ORDER_TOTAL)):
                raise AppError("That round is too large to send from a table. Please ask a member of staff.")
            order.subtotal, order.tax, order.total = subtotal, tax, total

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
        return [QrTableRead(table_id=t.id, table_number=t.table_number, zone=t.zone, qr_token=t.qr_token, has_open_session=t.id in open_ids) for t in tables]

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
        out = []
        for s in sessions:
            guests = self.db.scalar(select(func.count()).select_from(SessionGuest).where(SessionGuest.session_id == s.id)) or 0
            rounds = self.db.execute(select(func.count(), func.coalesce(func.sum(Order.total), 0)).where(
                Order.table_session_id == s.id, Order.status.notin_(CLOSED_STATUSES))).one()
            asked = list(self.db.scalars(select(ServiceRequest.kind).where(
                ServiceRequest.table_session_id == s.id, ServiceRequest.state == REQUEST_OPEN).order_by(ServiceRequest.id)))
            out.append(OpenSessionRead(
                session_id=s.id, table_id=s.table_id, table_number=s.table.table_number, opened_at=s.opened_at,
                guests=guests, rounds=rounds[0], total=Decimal(rounds[1]), requests=asked,
            ))
        return out

    def close_session(self, session_id: int, restaurant_id: int, staff_user_id: int | None) -> None:
        """End the tab: every guest pass stops working, the table goes to cleaning and its QR code is replaced,
        so a photo of the old code is worthless."""
        session = self.db.get(TableSession, session_id)
        if session is None or session.restaurant_id != restaurant_id:
            raise NotFoundError("Session not found")
        if session.state != OPEN:
            raise AppError("This session is already closed")
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
        ready = dict(self.db.execute(
            select(Order.table_session_id, func.count()).where(
                Order.restaurant_id == restaurant_id, Order.table_session_id.is_not(None), Order.status == OrderStatus.READY)
            .group_by(Order.table_session_id)
        ).all())
        waiting = dict(self.db.execute(
            select(ServiceRequest.table_session_id, func.min(ServiceRequest.created_at)).where(
                ServiceRequest.restaurant_id == restaurant_id, ServiceRequest.state == REQUEST_OPEN)
            .group_by(ServiceRequest.table_session_id)
        ).all())
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

    def _table(self, table_id: int, restaurant_id: int) -> RestaurantTable:
        table = self.db.get(RestaurantTable, table_id)
        if table is None or table.restaurant_id != restaurant_id:
            raise NotFoundError("Table not found")
        return table
