"""Reservation booking, availability and table floor-status logic.

Floor status (`RestaurantTable.status`) is *derived* from reservations:
  SEATED reservation running now          -> OCCUPIED
  booking starting within NEAR_TERM window -> RESERVED
  otherwise                                -> AVAILABLE
CLEANING is a manual staff state and is never overwritten by the derivation.

The session factory runs with autoflush disabled, so every derivation flushes pending
reservation changes first — otherwise it would read stale rows.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, joinedload

from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.core.hours import status_at
from app.core.security import create_reservation_action_token, decode_reservation_action_token
from app.core.tenancy import site_url
from app.models.enums import ReservationStatus, TableStatus
from app.models.reservation import Reservation
from app.models.restaurant_table import RestaurantTable
from app.models.user import User
from app.repositories.restaurant import RestaurantRepository
from app.services.notifications import (
    cancel_reservation_reminder,
    notify_reservation_cancelled,
    notify_reservation_confirmed,
    notify_reservation_reminder,
)
from app.schemas.reservation import (
    AdminAvailabilityResponse,
    AdminReservationCreate,
    AdminTableAvailability,
    AvailabilityResponse,
    AvailableTableRead,
    FloorTableRead,
    ReservationConflict,
    ReservationCreate,
    ReservationExtend,
    ReservationRead,
    ReservationStatusUpdate,
    ReservationUpdate,
    TableReservationBrief,
)

DEFAULT_DURATION_MINUTES = 90
HOLD_MINUTES = 15
NEAR_TERM_MINUTES = 120  # bookings starting sooner than this make the table RESERVED
FLOOR_BLOCK_MINUTES = 15  # OCCUPIED/CLEANING tables can't start a new slot inside this window
EARLY_SEAT_MINUTES = 60  # staff may seat a party up to this long before their booked time
MAX_ADVANCE_DAYS = 90
PAST_GRACE_MINUTES = 5
SUGGESTION_OFFSETS_MINUTES = (30, -30, 60, -60, 90, -90, 120, -120, 180, -180)
# Seated guests still marked seated this long after their booked end are assumed gone (staff
# forgot to click Complete) and are closed automatically. Before that they show as "overdue".
OVERSTAY_AUTO_COMPLETE_MINUTES = 60
MAX_TOTAL_MINUTES = 8 * 60  # longest a single booking can be stretched to by extending
BLOCKED_LOOKAHEAD_MINUTES = 15  # warn when a due booking's table is still occupied
_NO_BUFFER = timedelta(0)

ACTIVE_STATUSES = (
    ReservationStatus.HELD,
    ReservationStatus.CONFIRMED,
    ReservationStatus.SEATED,
)

ALLOWED_TRANSITIONS: dict[ReservationStatus, set[ReservationStatus]] = {
    ReservationStatus.HELD: {
        ReservationStatus.CONFIRMED,
        ReservationStatus.SEATED,
        ReservationStatus.CANCELLED,
        ReservationStatus.EXPIRED,
    },
    ReservationStatus.CONFIRMED: {ReservationStatus.SEATED, ReservationStatus.CANCELLED},
    ReservationStatus.SEATED: {ReservationStatus.COMPLETED},
    ReservationStatus.COMPLETED: set(),
    ReservationStatus.CANCELLED: set(),
    ReservationStatus.EXPIRED: set(),
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _status_value(value) -> str:
    return value.value if hasattr(value, "value") else str(value)


class ReservationService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.restaurants = RestaurantRepository(db)

    # ------------------------------------------------------------------ housekeeping

    def expire_holds(self, restaurant_id: int | None = None, *, commit: bool = True) -> int:
        """Lazily close stale reservations.

        - HELD past `hold_expires_at`                       -> EXPIRED
        - HELD/CONFIRMED whose booked window has fully passed -> COMPLETED if an order is
          attached (they dined), otherwise EXPIRED (no-show)
        - SEATED and still open long after their booked end -> COMPLETED (forgotten check-out)
        """
        now = _utcnow()
        stmt = select(Reservation).where(
            or_(
                and_(
                    Reservation.status == ReservationStatus.HELD,
                    Reservation.hold_expires_at.is_not(None),
                    Reservation.hold_expires_at < now,
                ),
                and_(
                    Reservation.status.in_([ReservationStatus.HELD, ReservationStatus.CONFIRMED]),
                    Reservation.ends_at < now,
                ),
                and_(
                    Reservation.status == ReservationStatus.SEATED,
                    Reservation.ends_at < now - timedelta(minutes=OVERSTAY_AUTO_COMPLETE_MINUTES),
                ),
            )
        )
        if restaurant_id is not None:
            stmt = stmt.where(Reservation.restaurant_id == restaurant_id)
        stale = list(self.db.scalars(stmt).all())
        if not stale:
            return 0

        table_ids: set[int] = set()
        for reservation in stale:
            lapsed_hold = (
                reservation.status == ReservationStatus.HELD
                and reservation.hold_expires_at is not None
                and reservation.hold_expires_at < now
            )
            if reservation.status == ReservationStatus.SEATED:
                reservation.status = ReservationStatus.COMPLETED
            elif not lapsed_hold and reservation.order_id is not None:
                reservation.status = ReservationStatus.COMPLETED
            else:
                reservation.status = ReservationStatus.EXPIRED
            reservation.hold_expires_at = None
            table_ids.add(reservation.table_id)
        self.db.flush()
        for table_id in table_ids:
            self._sync_table_floor_status(table_id)
        if commit:
            self.db.commit()
        return len(stale)

    def refresh_floor_status(self, restaurant_id: int) -> None:
        """Re-derive AVAILABLE/RESERVED tables from the clock (a booking may have come into
        range or lapsed since the last event). OCCUPIED/CLEANING are left alone."""
        self.expire_holds(restaurant_id, commit=False)
        tables = self.db.scalars(
            select(RestaurantTable).where(
                RestaurantTable.restaurant_id == restaurant_id,
                RestaurantTable.is_active.is_(True),
                RestaurantTable.status.in_([TableStatus.AVAILABLE, TableStatus.RESERVED]),
            )
        ).all()
        for table in tables:
            self._sync_table_floor_status(table.id, keep_occupied=True)
        self.db.commit()

    # ------------------------------------------------------------------ availability

    def get_availability(
        self,
        restaurant_id: int,
        starts_at: datetime,
        party_size: int,
        duration_minutes: int = DEFAULT_DURATION_MINUTES,
    ) -> AvailabilityResponse:
        self.expire_holds(restaurant_id)
        restaurant = self._active_restaurant(restaurant_id)
        if not restaurant.dine_in_enabled:
            raise AppError("Dine-in is not available for this restaurant")

        starts_at = self._ensure_aware(starts_at)
        self._validate_start(starts_at)
        self._require_open(restaurant, starts_at)
        ends_at = starts_at + timedelta(minutes=duration_minutes)

        tables = self._available_tables(restaurant_id, starts_at, ends_at, party_size)
        available_ids = {t.id for t in tables}
        floor = [
            FloorTableRead(
                id=t.id,
                table_number=t.table_number,
                capacity=t.capacity,
                zone=t.zone,
                shape=t.shape,
                pos_x=t.pos_x,
                pos_y=t.pos_y,
                state=(
                    "TOO_SMALL"
                    if t.capacity < party_size
                    else "AVAILABLE" if t.id in available_ids else "UNAVAILABLE"
                ),
            )
            for t in self._active_tables(restaurant_id)
        ]
        suggestions = (
            [] if tables else self._suggest_times(restaurant_id, starts_at, party_size, duration_minutes)
        )
        return AvailabilityResponse(
            starts_at=starts_at,
            ends_at=ends_at,
            party_size=party_size,
            tables=[
                AvailableTableRead(
                    id=table.id,
                    table_number=table.table_number,
                    capacity=table.capacity,
                    zone=table.zone,
                    status=TableStatus.AVAILABLE.value,
                )
                for table in tables
            ],
            floor=floor,
            suggested_times=suggestions,
        )

    def get_admin_availability(
        self,
        restaurant_id: int,
        starts_at: datetime,
        party_size: int,
        duration_minutes: int = DEFAULT_DURATION_MINUTES,
        exclude_reservation_id: int | None = None,
    ) -> AdminAvailabilityResponse:
        """Per-table status for the requested slot (not for 'now')."""
        self.expire_holds(restaurant_id)
        self._active_restaurant(restaurant_id)

        starts_at = self._ensure_aware(starts_at)
        ends_at = starts_at + timedelta(minutes=duration_minutes)
        buffer = self._buffer(restaurant_id)
        tables = self._active_tables(restaurant_id)

        results: list[AdminTableAvailability] = []
        for table in tables:
            conflicts = self._conflicts(
                table.id, starts_at, ends_at, exclude_id=exclude_reservation_id, buffer=buffer
            )
            floor_blocked = self._floor_blocks_slot(table, starts_at)
            if floor_blocked and not conflicts:
                # Guests are physically still there (e.g. running over) — say who.
                conflicts = [r for r in self._seated_on(table.id) if r.id != exclude_reservation_id]
            too_small = table.capacity < party_size

            if conflicts:
                slot_status = (
                    TableStatus.OCCUPIED.value
                    if any(c.status == ReservationStatus.SEATED for c in conflicts)
                    else TableStatus.RESERVED.value
                )
            elif floor_blocked:
                slot_status = _status_value(table.status)
            elif too_small:
                slot_status = "TOO_SMALL"
            else:
                slot_status = TableStatus.AVAILABLE.value

            results.append(
                AdminTableAvailability(
                    id=table.id,
                    table_number=table.table_number,
                    capacity=table.capacity,
                    zone=table.zone,
                    shape=table.shape,
                    pos_x=table.pos_x,
                    pos_y=table.pos_y,
                    floor_status=_status_value(table.status),
                    slot_status=slot_status,
                    available=slot_status == TableStatus.AVAILABLE.value,
                    conflicts=[
                        ReservationConflict(
                            id=c.id,
                            guest_name=c.guest_name,
                            party_size=c.party_size,
                            starts_at=c.starts_at,
                            ends_at=c.ends_at,
                            status=c.status,
                        )
                        for c in conflicts
                    ],
                )
            )
        return AdminAvailabilityResponse(
            starts_at=starts_at,
            ends_at=ends_at,
            party_size=party_size,
            tables=results,
        )

    # ------------------------------------------------------------------ create

    def create_reservation(
        self,
        restaurant_id: int,
        data: ReservationCreate,
        user: User | None,
        *,
        seat_immediately: bool = False,
        enforce_hours: bool = True,
    ) -> ReservationRead:
        self.expire_holds(restaurant_id)
        restaurant = self._active_restaurant(restaurant_id)
        if not restaurant.dine_in_enabled:
            raise AppError("Dine-in is not available for this restaurant")

        table = self.db.get(RestaurantTable, data.table_id)
        if table is None or table.restaurant_id != restaurant_id:
            raise AppError("Invalid table for this restaurant")
        if not table.is_active:
            raise AppError(f"Table {table.table_number} is not in service")
        if table.capacity < data.party_size:
            raise AppError("Table capacity is too small for this party")

        if seat_immediately:
            starts_at = _utcnow()  # walk-ins are seated now, whatever the client clock says
        else:
            starts_at = self._ensure_aware(data.starts_at)
            self._validate_start(starts_at)
            if enforce_hours:
                self._require_open(restaurant, starts_at)
        ends_at = starts_at + timedelta(minutes=data.duration_minutes)

        # Lock the table row to serialise concurrent bookings of the same table.
        locked = self.db.scalar(
            select(RestaurantTable).where(RestaurantTable.id == table.id).with_for_update()
        )
        if locked is None:
            raise AppError("Table not found")

        buffer = timedelta(minutes=restaurant.reservation_buffer_minutes)
        if seat_immediately:
            self._ensure_table_has_no_seated_guests(table)
        if self._has_overlap(table.id, starts_at, ends_at, buffer=buffer):
            raise AppError(f"Table {table.table_number} is already booked for that time")
        if self._floor_blocks_slot(locked, starts_at):
            raise AppError(f"Table {table.table_number} is currently unavailable")
        if user is not None:
            self._ensure_no_user_overlap(user.id, restaurant_id, starts_at, ends_at)

        if seat_immediately:
            status = ReservationStatus.SEATED
            hold_expires_at = None
        elif data.hold:
            status = ReservationStatus.HELD
            hold_expires_at = _utcnow() + timedelta(minutes=HOLD_MINUTES)
        else:
            status = ReservationStatus.CONFIRMED
            hold_expires_at = None

        reservation = Reservation(
            restaurant_id=restaurant_id,
            table_id=table.id,
            user_id=user.id if user else None,
            party_size=data.party_size,
            starts_at=starts_at,
            ends_at=ends_at,
            status=status,
            hold_expires_at=hold_expires_at,
            guest_name=data.guest_name.strip(),
            guest_email=str(data.guest_email) if data.guest_email else (user.email if user else None),
            guest_phone=data.guest_phone or (user.phone if user else None),
            notes=data.notes,
        )
        self.db.add(reservation)
        self.db.flush()
        if seat_immediately:
            locked.status = TableStatus.OCCUPIED
        else:
            self._sync_table_floor_status(table.id, keep_occupied=True)
        if status == ReservationStatus.CONFIRMED:  # (walk-ins and short-lived holds aren't emailed)
            notify_reservation_confirmed(self.db, restaurant, reservation, table.table_number, self.action_link(reservation, restaurant))
            self._schedule_reminder(restaurant, reservation, table.table_number)
        self.db.commit()
        self.db.refresh(reservation)
        return self._to_read(reservation)

    def create_admin_reservation(self, restaurant_id: int, data: AdminReservationCreate) -> ReservationRead:
        user = self.db.get(User, data.user_id) if data.user_id else None
        return self.create_reservation(
            restaurant_id,
            data,
            user,
            seat_immediately=data.seat_immediately,
            enforce_hours=False,  # staff may book outside posted hours (private events, corrections)
        )

    # ------------------------------------------------------------------ read

    def list_restaurant_reservations(
        self,
        restaurant_id: int,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        status: ReservationStatus | None = None,
    ) -> list[ReservationRead]:
        """Reservations whose start falls in [start, end), earliest first."""
        self.expire_holds(restaurant_id)
        stmt = (
            select(Reservation)
            .options(joinedload(Reservation.table))
            .where(Reservation.restaurant_id == restaurant_id)
            .order_by(Reservation.starts_at.asc(), Reservation.id.asc())
        )
        if start is not None:
            stmt = stmt.where(Reservation.starts_at >= self._ensure_aware(start))
        if end is not None:
            stmt = stmt.where(Reservation.starts_at < self._ensure_aware(end))
        if status is not None:
            stmt = stmt.where(Reservation.status == status)
        return [self._to_read(r) for r in self.db.scalars(stmt).unique().all()]

    def list_user_reservations(
        self,
        user_id: int,
        restaurant_id: int | None = None,
        *,
        include_past: bool = False,
    ) -> list[ReservationRead]:
        self.expire_holds(restaurant_id)
        now = _utcnow()
        stmt = (
            select(Reservation)
            .options(joinedload(Reservation.table))
            .where(Reservation.user_id == user_id)
        )
        if restaurant_id is not None:
            stmt = stmt.where(Reservation.restaurant_id == restaurant_id)
        if include_past:
            stmt = stmt.order_by(Reservation.starts_at.desc())
        else:
            stmt = stmt.where(
                Reservation.status.in_(list(ACTIVE_STATUSES)),
                or_(Reservation.status == ReservationStatus.SEATED, Reservation.ends_at > now),
            ).order_by(Reservation.starts_at.asc())
        return [self._to_read(r) for r in self.db.scalars(stmt).unique().all()]

    def get_reservation(
        self,
        reservation_id: int,
        restaurant_id: int | None = None,
        *,
        expire: bool = True,
    ) -> Reservation:
        # `expire=False` avoids committing in the middle of a caller's own transaction.
        if expire:
            self.expire_holds(restaurant_id)
        reservation = self.db.scalar(
            select(Reservation)
            .options(joinedload(Reservation.table))
            .where(Reservation.id == reservation_id)
        )
        if reservation is None:
            raise NotFoundError("Reservation not found")
        if restaurant_id is not None and reservation.restaurant_id != restaurant_id:
            raise NotFoundError("Reservation not found")
        if (
            reservation.status == ReservationStatus.HELD
            and reservation.hold_expires_at
            and reservation.hold_expires_at < _utcnow()
        ):
            raise AppError("This reservation hold has expired")
        return reservation

    # ------------------------------------------------------------------ customer actions

    def confirm_hold(self, reservation_id: int, user_id: int) -> ReservationRead:
        reservation = self.get_reservation(reservation_id)
        if reservation.user_id != user_id:
            raise AppError("You cannot confirm this reservation")
        if reservation.status != ReservationStatus.HELD:
            raise AppError("Only held reservations can be confirmed")
        reservation.status = ReservationStatus.CONFIRMED
        reservation.hold_expires_at = None
        self._sync_table_floor_status(reservation.table_id, keep_occupied=True)
        restaurant = self.restaurants.get_by_id(reservation.restaurant_id)
        if restaurant is not None and reservation.guest_email:
            table_number = reservation.table.table_number if reservation.table else None
            notify_reservation_confirmed(self.db, restaurant, reservation, table_number, self.action_link(reservation, restaurant))
            self._schedule_reminder(restaurant, reservation, table_number)
        self.db.commit()
        self.db.refresh(reservation)
        return self._to_read(reservation)

    def cancel_reservation(self, reservation_id: int, user_id: int) -> ReservationRead:
        reservation = self.get_reservation(reservation_id)
        if reservation.user_id != user_id:
            raise AppError("You cannot cancel this reservation")
        return self._cancel(reservation)

    def _cancel(self, reservation: Reservation) -> ReservationRead:
        if reservation.status not in (ReservationStatus.HELD, ReservationStatus.CONFIRMED):
            raise AppError("This reservation can no longer be cancelled")
        if reservation.order_id is not None:
            raise AppError("This reservation has an order attached. Please contact the restaurant to cancel.")
        reservation.status = ReservationStatus.CANCELLED
        reservation.hold_expires_at = None
        self._sync_table_floor_status(reservation.table_id)
        self._email_cancellation(reservation)
        self.db.commit()
        self.db.refresh(reservation)
        return self._to_read(reservation)

    # ------------------------------------------------------------------ acting from an emailed link (no account)

    def _issue_action_token(self, reservation: Reservation) -> str:
        expires_at = max(reservation.starts_at + timedelta(hours=3), _utcnow() + timedelta(hours=1))
        return create_reservation_action_token(reservation.id, reservation.restaurant_id, expires_at)

    def action_link(self, reservation: Reservation, restaurant) -> str:
        return f"{site_url(restaurant)}/reservations/manage?token={self._issue_action_token(reservation)}"

    def _from_action_token(self, token: str) -> Reservation:
        try:
            payload = decode_reservation_action_token(token)
            reservation_id, restaurant_id = int(payload["sub"]), int(payload["tenant"])
        except (ValueError, KeyError, TypeError):
            raise AppError("This link is invalid or has expired. Please contact the restaurant.") from None
        return self.get_reservation(reservation_id, restaurant_id, expire=False)

    def get_by_action_token(self, token: str) -> ReservationRead:
        return self._to_read(self._from_action_token(token))

    def confirm_attendance(self, token: str) -> ReservationRead:
        reservation = self._from_action_token(token)
        if reservation.status not in (ReservationStatus.CONFIRMED, ReservationStatus.SEATED):
            raise AppError("This reservation can no longer be confirmed")
        reservation.guest_confirmed_at = _utcnow()
        self.db.commit()
        self.db.refresh(reservation)
        return self._to_read(reservation)

    def cancel_by_token(self, token: str) -> ReservationRead:
        return self._cancel(self._from_action_token(token))

    # ------------------------------------------------------------------ staff actions

    def update_status(
        self,
        reservation_id: int,
        restaurant_id: int,
        data: ReservationStatusUpdate,
    ) -> ReservationRead:
        reservation = self.get_reservation(reservation_id, restaurant_id)
        current = reservation.status
        target = data.status

        if target != current:
            if target not in ALLOWED_TRANSITIONS.get(current, set()):
                raise AppError(
                    f"Cannot change a {_status_value(current).lower()} reservation to {_status_value(target).lower()}"
                )
            now = _utcnow()
            if target == ReservationStatus.SEATED:
                self._seat(reservation, now)
            elif target == ReservationStatus.COMPLETED:
                # Guests left: free whatever is left of the booked window.
                if reservation.ends_at > now:
                    reservation.ends_at = max(now, reservation.starts_at + timedelta(minutes=1))
            reservation.status = target
            if target != ReservationStatus.HELD:
                reservation.hold_expires_at = None
            if target == ReservationStatus.CANCELLED:
                self._email_cancellation(reservation)
            elif current == ReservationStatus.CONFIRMED:
                # Leaving CONFIRMED some other way (seated, completed): nobody needs a reminder about a visit
                # that is already under way or over.
                cancel_reservation_reminder(self.db, reservation.id)
        if data.notes:
            reservation.notes = data.notes

        self.db.flush()
        if reservation.status == ReservationStatus.SEATED:
            table = self.db.get(RestaurantTable, reservation.table_id)
            if table is not None:
                table.status = TableStatus.OCCUPIED
        else:
            self._sync_table_floor_status(reservation.table_id)
        self.db.commit()
        self.db.refresh(reservation)
        return self._to_read(reservation)

    def update_reservation(
        self,
        reservation_id: int,
        restaurant_id: int,
        data: ReservationUpdate,
    ) -> ReservationRead:
        """Edit guest details, or move an upcoming booking to another time/table."""
        reservation = self.get_reservation(reservation_id, restaurant_id)
        if reservation.status not in (
            ReservationStatus.HELD,
            ReservationStatus.CONFIRMED,
            ReservationStatus.SEATED,
        ):
            raise AppError("Only active reservations can be edited")

        changes = data.model_dump(exclude_unset=True)
        schedule_keys = {"table_id", "party_size", "starts_at", "duration_minutes"}
        if reservation.status == ReservationStatus.SEATED and schedule_keys & changes.keys():
            raise AppError("Seated guests can't be moved — only their details can be edited")

        old_table_id = reservation.table_id
        table_id = changes.get("table_id") or reservation.table_id
        party_size = changes.get("party_size") or reservation.party_size
        current_minutes = int((reservation.ends_at - reservation.starts_at).total_seconds() // 60)
        duration = changes.get("duration_minutes") or current_minutes
        starts_at = self._ensure_aware(changes["starts_at"]) if changes.get("starts_at") else reservation.starts_at
        ends_at = starts_at + timedelta(minutes=duration)

        moved = (
            table_id != reservation.table_id
            or starts_at != reservation.starts_at
            or ends_at != reservation.ends_at
            or party_size != reservation.party_size
        )
        if moved:
            table = self.db.get(RestaurantTable, table_id)
            if table is None or table.restaurant_id != restaurant_id:
                raise AppError("Invalid table for this restaurant")
            if not table.is_active and table.id != reservation.table_id:
                raise AppError(f"Table {table.table_number} is not in service")
            if table.capacity < party_size:
                raise AppError("Table capacity is too small for this party")
            if starts_at != reservation.starts_at:
                self._validate_start(starts_at)
            locked = self.db.scalar(
                select(RestaurantTable).where(RestaurantTable.id == table.id).with_for_update()
            )
            buffer = self._buffer(restaurant_id)
            if self._has_overlap(table.id, starts_at, ends_at, exclude_id=reservation.id, buffer=buffer):
                raise AppError(f"Table {table.table_number} is already booked for that time")
            if (table_id != reservation.table_id or starts_at != reservation.starts_at) and locked is not None:
                if self._floor_blocks_slot(locked, starts_at):
                    raise AppError(f"Table {table.table_number} is currently unavailable")
            if reservation.user_id is not None:
                self._ensure_no_user_overlap(
                    reservation.user_id, restaurant_id, starts_at, ends_at, exclude_id=reservation.id
                )
            reservation.table_id = table_id
            reservation.party_size = party_size
            reservation.starts_at = starts_at
            reservation.ends_at = ends_at

        for key in ("guest_name", "guest_email", "guest_phone", "notes"):
            if key in changes:
                value = changes[key]
                setattr(reservation, key, str(value) if key == "guest_email" and value else value)

        self.db.flush()
        for table_id_to_sync in {old_table_id, reservation.table_id}:
            self._sync_table_floor_status(table_id_to_sync, keep_occupied=True)
        if reservation.status == ReservationStatus.CONFIRMED:
            # The time, table or contact details may have changed: replace whatever reminder was queued before.
            restaurant = self.restaurants.get_by_id(restaurant_id)
            new_table = self.db.get(RestaurantTable, reservation.table_id)
            self._schedule_reminder(restaurant, reservation, new_table.table_number if new_table else None)
        self.db.commit()
        self.db.refresh(reservation)
        return self._to_read(reservation)

    # ------------------------------------------------------------------ order linkage

    def attach_to_order(self, reservation_id: int, order_id: int, user_id: int, restaurant_id: int) -> Reservation:
        reservation = self.get_reservation(reservation_id, restaurant_id, expire=False)
        if reservation.user_id is not None and reservation.user_id != user_id:
            raise AppError("Reservation does not belong to this customer")
        if reservation.status == ReservationStatus.HELD:
            reservation.status = ReservationStatus.CONFIRMED
            reservation.hold_expires_at = None
        if reservation.status not in (ReservationStatus.CONFIRMED, ReservationStatus.SEATED):
            raise AppError("Reservation is not valid for ordering")
        if reservation.order_id is not None and reservation.order_id != order_id:
            raise AppError("Reservation is already linked to another order")
        reservation.order_id = order_id
        # Ordering at the table means the party has arrived — but only once their time has come.
        # An order placed days ahead must not flip a future booking to SEATED.
        if (
            reservation.status == ReservationStatus.CONFIRMED
            and reservation.starts_at <= _utcnow()
            and not [r for r in self._seated_on(reservation.table_id) if r.id != reservation.id]
        ):
            reservation.status = ReservationStatus.SEATED
        self._sync_table_floor_status(reservation.table_id, keep_occupied=True)
        return reservation

    # ------------------------------------------------------------------ table release (staff)

    def blocking_reservations(self, table_id: int) -> list[Reservation]:
        """Reservations currently responsible for the table being RESERVED/OCCUPIED."""
        now = _utcnow()
        horizon = now + timedelta(minutes=NEAR_TERM_MINUTES)
        return [
            r
            for r in self._active_for_table(table_id)
            if r.status == ReservationStatus.SEATED or r.starts_at <= horizon
        ]

    def release_table(
        self,
        table: RestaurantTable,
        target: TableStatus,
        *,
        force: bool,
    ) -> tuple[int, int]:
        """Set a table AVAILABLE/CLEANING, resolving reservations that hold it.

        Seated parties are marked COMPLETED (they left); reservations about to start are
        CANCELLED. Later bookings are untouched. Returns (cancelled, completed).
        """
        blocking = self.blocking_reservations(table.id)
        if blocking and not force:
            names = ", ".join(f"{r.guest_name} (party of {r.party_size})" for r in blocking)
            raise ConflictError(f"Table {table.table_number} has an active reservation: {names}")

        now = _utcnow()
        cancelled = completed = 0
        for reservation in blocking:
            if reservation.status == ReservationStatus.SEATED:
                reservation.status = ReservationStatus.COMPLETED
                if reservation.ends_at > now:
                    reservation.ends_at = max(now, reservation.starts_at + timedelta(minutes=1))
                completed += 1
            else:
                reservation.status = ReservationStatus.CANCELLED
                cancelled += 1
                self._email_cancellation(reservation, table)
            reservation.hold_expires_at = None
        self.db.flush()
        table.status = target
        return cancelled, completed

    def table_overview(
        self, restaurant_id: int, include_inactive: bool = False
    ) -> list[tuple[RestaurantTable, list[TableReservationBrief]]]:
        """Tables plus their live/upcoming (next 24h) reservations, for the floor dashboard."""
        self.refresh_floor_status(restaurant_id)
        now = _utcnow()
        horizon = now + timedelta(minutes=NEAR_TERM_MINUTES)
        tables = self._active_tables(restaurant_id, include_inactive=include_inactive)
        rows = self.db.scalars(
            select(Reservation)
            .where(
                Reservation.restaurant_id == restaurant_id,
                Reservation.status.in_(list(ACTIVE_STATUSES)),
                or_(
                    Reservation.status != ReservationStatus.HELD,
                    and_(Reservation.hold_expires_at.is_not(None), Reservation.hold_expires_at > now),
                ),
                or_(Reservation.status == ReservationStatus.SEATED, Reservation.ends_at > now),
                Reservation.starts_at < now + timedelta(hours=24),
            )
            .order_by(Reservation.starts_at)
        ).all()
        by_table: dict[int, list[TableReservationBrief]] = {}
        for r in rows:
            by_table.setdefault(r.table_id, []).append(
                TableReservationBrief(
                    id=r.id,
                    guest_name=r.guest_name,
                    guest_phone=r.guest_phone,
                    party_size=r.party_size,
                    starts_at=r.starts_at,
                    ends_at=r.ends_at,
                    status=r.status,
                    blocking=r.status == ReservationStatus.SEATED or r.starts_at <= horizon,
                    overdue_minutes=self._overdue_minutes(r, now),
                )
            )
        return [(t, by_table.get(t.id, [])) for t in tables]

    # ------------------------------------------------------------------ internals

    def _email_cancellation(self, reservation: Reservation, table: RestaurantTable | None = None) -> None:
        """Tell the guest (if we have their email), and drop any reminder queued for this booking. Queued in the
        caller's transaction."""
        cancel_reservation_reminder(self.db, reservation.id)
        if not reservation.guest_email:
            return
        restaurant = self.restaurants.get_by_id(reservation.restaurant_id)
        table = table or reservation.table or self.db.get(RestaurantTable, reservation.table_id)
        if restaurant is not None:
            notify_reservation_cancelled(self.db, restaurant, reservation, table.table_number if table else None)

    def _active_restaurant(self, restaurant_id: int):
        restaurant = self.restaurants.get_by_id(restaurant_id)
        if restaurant is None or not restaurant.is_active:
            raise NotFoundError("Restaurant not found")
        return restaurant

    # A reminder is only worth sending if there is enough notice for it to add something beyond the
    # confirmation email the guest already got.
    REMINDER_LEAD_HOURS = 3

    def _schedule_reminder(self, restaurant, reservation: Reservation, table_number: str | None) -> None:
        if restaurant is None or not reservation.guest_email:
            return
        cancel_reservation_reminder(self.db, reservation.id)  # replace whatever was queued before, if anything
        lead = reservation.starts_at - _utcnow()
        if lead < timedelta(hours=self.REMINDER_LEAD_HOURS + 0.5):
            return  # too soon for a separate reminder to be useful
        run_at = reservation.starts_at - timedelta(hours=self.REMINDER_LEAD_HOURS)
        notify_reservation_reminder(self.db, restaurant, reservation, table_number, run_at, self.action_link(reservation, restaurant))

    def _require_open(self, restaurant, starts_at: datetime) -> None:
        status = status_at(restaurant, starts_at)
        if not status.open:
            raise AppError(f"{restaurant.name} is closed at that time ({status.reason}). Please choose another time.")

    def _validate_start(self, starts_at: datetime) -> None:
        now = _utcnow()
        if starts_at < now - timedelta(minutes=PAST_GRACE_MINUTES):
            raise AppError("Reservation time must be in the future")
        if starts_at > now + timedelta(days=MAX_ADVANCE_DAYS):
            raise AppError(f"Reservations can be made up to {MAX_ADVANCE_DAYS} days in advance")

    def _seat(self, reservation: Reservation, now: datetime) -> None:
        """Mark arrival. Seating early pulls the start forward, provided the table is free."""
        table = reservation.table or self.db.get(RestaurantTable, reservation.table_id)
        self._ensure_table_has_no_seated_guests(table, exclude_id=reservation.id)
        if reservation.starts_at > now:
            if reservation.starts_at - now > timedelta(minutes=EARLY_SEAT_MINUTES):
                raise AppError(
                    f"Too early to seat — this reservation starts in more than {EARLY_SEAT_MINUTES} minutes"
                )
            if self._conflicts(reservation.table_id, now, reservation.starts_at, exclude_id=reservation.id):
                raise AppError("The table is still booked by an earlier reservation")
            reservation.starts_at = now

    def _conflicts(
        self,
        table_id: int,
        starts_at: datetime,
        ends_at: datetime,
        exclude_id: int | None = None,
        buffer: timedelta = _NO_BUFFER,
    ) -> list[Reservation]:
        """Active bookings overlapping [starts_at, ends_at), padded by `buffer` on both sides so
        parties are never packed back-to-back (clearing time + slack for guests running over)."""
        now = _utcnow()
        conditions = [
            Reservation.table_id == table_id,
            Reservation.status.in_(list(ACTIVE_STATUSES)),
            Reservation.starts_at < ends_at + buffer,
            Reservation.ends_at > starts_at - buffer,
            or_(
                Reservation.status != ReservationStatus.HELD,
                and_(Reservation.hold_expires_at.is_not(None), Reservation.hold_expires_at > now),
            ),
        ]
        if exclude_id is not None:
            conditions.append(Reservation.id != exclude_id)
        return list(self.db.scalars(select(Reservation).where(*conditions).order_by(Reservation.starts_at)).all())

    def _has_overlap(
        self,
        table_id: int,
        starts_at: datetime,
        ends_at: datetime,
        exclude_id: int | None = None,
        buffer: timedelta = _NO_BUFFER,
    ) -> bool:
        return bool(self._conflicts(table_id, starts_at, ends_at, exclude_id, buffer))

    def _ensure_no_user_overlap(
        self,
        user_id: int,
        restaurant_id: int,
        starts_at: datetime,
        ends_at: datetime,
        exclude_id: int | None = None,
    ) -> None:
        now = _utcnow()
        conditions = [
            Reservation.user_id == user_id,
            Reservation.restaurant_id == restaurant_id,
            Reservation.status.in_(list(ACTIVE_STATUSES)),
            Reservation.starts_at < ends_at,
            Reservation.ends_at > starts_at,
            or_(
                Reservation.status != ReservationStatus.HELD,
                and_(Reservation.hold_expires_at.is_not(None), Reservation.hold_expires_at > now),
            ),
        ]
        if exclude_id is not None:
            conditions.append(Reservation.id != exclude_id)
        if self.db.scalar(select(Reservation.id).where(*conditions).limit(1)) is not None:
            raise AppError("You already have a reservation at this time")

    def _active_for_table(self, table_id: int) -> list[Reservation]:
        """Reservations that still matter for the floor: unexpired, not finished.
        SEATED ones count until staff completes them, even if the booked window has passed."""
        now = _utcnow()
        stmt = (
            select(Reservation)
            .where(
                Reservation.table_id == table_id,
                Reservation.status.in_(list(ACTIVE_STATUSES)),
                or_(
                    Reservation.status != ReservationStatus.HELD,
                    and_(Reservation.hold_expires_at.is_not(None), Reservation.hold_expires_at > now),
                ),
                or_(Reservation.status == ReservationStatus.SEATED, Reservation.ends_at > now),
            )
            .order_by(Reservation.starts_at)
        )
        return list(self.db.scalars(stmt).all())

    def _floor_blocks_slot(self, table: RestaurantTable, starts_at: datetime) -> bool:
        """OCCUPIED/CLEANING only blocks slots starting right now, not later ones."""
        if table.status not in (TableStatus.OCCUPIED, TableStatus.CLEANING):
            return False
        return starts_at <= _utcnow() + timedelta(minutes=FLOOR_BLOCK_MINUTES)

    def _available_tables(
        self,
        restaurant_id: int,
        starts_at: datetime,
        ends_at: datetime,
        party_size: int,
    ) -> list[RestaurantTable]:
        tables = self.db.scalars(
            select(RestaurantTable)
            .where(
                RestaurantTable.restaurant_id == restaurant_id,
                RestaurantTable.is_active.is_(True),
                RestaurantTable.capacity >= party_size,
            )
            .order_by(RestaurantTable.capacity, RestaurantTable.table_number)
        ).all()
        buffer = self._buffer(restaurant_id)
        return [
            t
            for t in tables
            if not self._has_overlap(t.id, starts_at, ends_at, buffer=buffer)
            and not self._floor_blocks_slot(t, starts_at)
        ]

    def _suggest_times(
        self,
        restaurant_id: int,
        starts_at: datetime,
        party_size: int,
        duration_minutes: int,
        limit: int = 4,
    ) -> list[datetime]:
        now = _utcnow()
        found: list[datetime] = []
        for offset in SUGGESTION_OFFSETS_MINUTES:
            candidate = starts_at + timedelta(minutes=offset)
            if candidate < now + timedelta(minutes=PAST_GRACE_MINUTES):
                continue
            if candidate > now + timedelta(days=MAX_ADVANCE_DAYS):
                continue
            ends = candidate + timedelta(minutes=duration_minutes)
            if self._available_tables(restaurant_id, candidate, ends, party_size):
                found.append(candidate)
                if len(found) >= limit:
                    break
        return sorted(found)

    def _sync_table_floor_status(self, table_id: int, *, keep_occupied: bool = False) -> None:
        """Re-derive a table's floor status from its reservations.

        `keep_occupied` protects a manually-set OCCUPIED (walk-in with no booking) from being
        reset by events that only add or refresh bookings; end-of-stay events pass False.
        """
        self.db.flush()  # autoflush is off — make pending status changes visible first
        table = self.db.get(RestaurantTable, table_id)
        if table is None or table.status == TableStatus.CLEANING:
            return
        if keep_occupied and table.status == TableStatus.OCCUPIED:
            return

        now = _utcnow()
        horizon = now + timedelta(minutes=NEAR_TERM_MINUTES)
        active = self._active_for_table(table_id)
        if any(r.status == ReservationStatus.SEATED and r.starts_at <= now for r in active):
            table.status = TableStatus.OCCUPIED
        elif any(r.starts_at <= horizon for r in active):
            table.status = TableStatus.RESERVED
        else:
            table.status = TableStatus.AVAILABLE

    def extend_reservation(
        self,
        reservation_id: int,
        restaurant_id: int,
        data: ReservationExtend,
    ) -> ReservationRead:
        """Give seated guests more time. Refused if the next booking would then clash — staff
        should move that booking to another table first."""
        reservation = self.get_reservation(reservation_id, restaurant_id)
        if reservation.status != ReservationStatus.SEATED:
            raise AppError("Only seated guests can be given more time")

        now = _utcnow()
        # Overdue guests are extended from now, not from a time that has long passed.
        new_end = max(reservation.ends_at, now) + timedelta(minutes=data.minutes)
        if new_end - reservation.starts_at > timedelta(minutes=MAX_TOTAL_MINUTES):
            raise AppError(f"A booking can't run longer than {MAX_TOTAL_MINUTES // 60} hours in total")

        clashes = self._conflicts(
            reservation.table_id,
            reservation.ends_at,
            new_end,
            exclude_id=reservation.id,
            buffer=self._buffer(restaurant_id),
        )
        if clashes:
            nxt = clashes[0]
            raise AppError(
                f"Can't extend — {nxt.guest_name} (party of {nxt.party_size}) is booked next on this table. "
                "Move that booking to another table first."
            )
        reservation.ends_at = new_end
        self.db.commit()
        self.db.refresh(reservation)
        return self._to_read(reservation)

    def _buffer(self, restaurant_id: int) -> timedelta:
        restaurant = self.restaurants.get_by_id(restaurant_id)
        return timedelta(minutes=restaurant.reservation_buffer_minutes if restaurant else 0)

    def _active_tables(self, restaurant_id: int, include_inactive: bool = False) -> list[RestaurantTable]:
        stmt = select(RestaurantTable).where(RestaurantTable.restaurant_id == restaurant_id)
        if not include_inactive:
            stmt = stmt.where(RestaurantTable.is_active.is_(True))
        return list(self.db.scalars(stmt.order_by(RestaurantTable.table_number)).all())

    def has_upcoming_bookings(self, table_id: int, min_party_size: int | None = None) -> list[Reservation]:
        """Active bookings (not yet finished) on a table, optionally only those needing more seats."""
        rows = self._active_for_table(table_id)
        if min_party_size is not None:
            rows = [r for r in rows if r.party_size > min_party_size]
        return rows

    def _seated_on(self, table_id: int) -> list[Reservation]:
        return list(
            self.db.scalars(
                select(Reservation)
                .where(Reservation.table_id == table_id, Reservation.status == ReservationStatus.SEATED)
                .order_by(Reservation.starts_at)
            ).all()
        )

    def _ensure_table_has_no_seated_guests(self, table: RestaurantTable, exclude_id: int | None = None) -> None:
        """One party per table: never seat a new party on top of one that hasn't been checked out."""
        others = [r for r in self._seated_on(table.id) if r.id != exclude_id]
        if not others:
            return
        current = others[0]
        overdue = self._overdue_minutes(current, _utcnow())
        detail = f", {overdue} min over their time" if overdue else ""
        raise AppError(
            f"Table {table.table_number} still has seated guests ({current.guest_name}{detail}). "
            "Complete their reservation, extend it, or seat this party at another table."
        )

    @staticmethod
    def _overdue_minutes(reservation: Reservation, now: datetime) -> int:
        if reservation.status != ReservationStatus.SEATED or reservation.ends_at >= now:
            return 0
        return int((now - reservation.ends_at).total_seconds() // 60)

    def _blocked_by(self, reservation: Reservation) -> str | None:
        """Name of the seated party occupying this booking's table when the booking is about due."""
        if reservation.status not in (ReservationStatus.HELD, ReservationStatus.CONFIRMED):
            return None
        if reservation.starts_at > _utcnow() + timedelta(minutes=BLOCKED_LOOKAHEAD_MINUTES):
            return None
        others = [r for r in self._seated_on(reservation.table_id) if r.id != reservation.id]
        return others[0].guest_name if others else None

    def _ensure_aware(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def _to_read(self, reservation: Reservation) -> ReservationRead:
        table = reservation.table
        if table is None:
            table = self.db.get(RestaurantTable, reservation.table_id)
        return ReservationRead(
            id=reservation.id,
            restaurant_id=reservation.restaurant_id,
            table_id=reservation.table_id,
            table_number=table.table_number if table else None,
            table_capacity=table.capacity if table else None,
            user_id=reservation.user_id,
            order_id=reservation.order_id,
            party_size=reservation.party_size,
            starts_at=reservation.starts_at,
            ends_at=reservation.ends_at,
            status=reservation.status,
            hold_expires_at=reservation.hold_expires_at,
            guest_name=reservation.guest_name,
            guest_email=reservation.guest_email,
            guest_phone=reservation.guest_phone,
            notes=reservation.notes,
            created_at=reservation.created_at,
            overdue_minutes=self._overdue_minutes(reservation, _utcnow()),
            blocked_by=self._blocked_by(reservation),
            guest_confirmed_at=reservation.guest_confirmed_at,
        )
