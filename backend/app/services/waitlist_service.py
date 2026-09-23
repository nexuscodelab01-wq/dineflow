"""Walk-in waitlist: a queue for guests with no table free yet.

Seating an entry hands off to `ReservationService` and creates a normal SEATED, seat-immediately
reservation (same as any other staff-seated walk-in) — so the table, kitchen and floor-plan logic
that already exists for a seated reservation is reused rather than duplicated here.
"""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AppError, NotFoundError
from app.models.enums import WaitlistStatus
from app.models.waitlist_entry import WaitlistEntry
from app.repositories.restaurant import RestaurantRepository
from app.schemas.reservation import AdminReservationCreate
from app.schemas.waitlist import WaitlistCreate, WaitlistRead, WaitlistSeat
from app.services.notifications import notify_waitlist_ready
from app.services.reservation_service import ReservationService


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class WaitlistService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.restaurants = RestaurantRepository(db)
        self.reservations = ReservationService(db)

    def _active_restaurant(self, restaurant_id: int):
        restaurant = self.restaurants.get_by_id(restaurant_id)
        if restaurant is None or not restaurant.is_active:
            raise NotFoundError("Restaurant not found")
        return restaurant

    def _get(self, entry_id: int, restaurant_id: int) -> WaitlistEntry:
        entry = self.db.get(WaitlistEntry, entry_id)
        if entry is None or entry.restaurant_id != restaurant_id:
            raise NotFoundError("Waitlist entry not found")
        return entry

    def _to_read(self, entry: WaitlistEntry) -> WaitlistRead:
        anchor = entry.notified_at or entry.created_at
        waiting_minutes = max(0, int((_utcnow() - anchor).total_seconds() // 60))
        return WaitlistRead(
            id=entry.id, guest_name=entry.guest_name, guest_email=entry.guest_email, guest_phone=entry.guest_phone,
            party_size=entry.party_size, notes=entry.notes, quoted_minutes=entry.quoted_minutes, status=entry.status,
            notified_at=entry.notified_at, reservation_id=entry.reservation_id, created_at=entry.created_at,
            waiting_minutes=waiting_minutes,
        )

    def add(self, restaurant_id: int, data: WaitlistCreate) -> WaitlistRead:
        self._active_restaurant(restaurant_id)
        entry = WaitlistEntry(
            restaurant_id=restaurant_id, guest_name=data.guest_name.strip(),
            guest_email=str(data.guest_email) if data.guest_email else None, guest_phone=data.guest_phone,
            party_size=data.party_size, notes=data.notes, quoted_minutes=data.quoted_minutes,
            status=WaitlistStatus.WAITING,
        )
        self.db.add(entry)
        self.db.commit()
        self.db.refresh(entry)
        return self._to_read(entry)

    def list_active(self, restaurant_id: int) -> list[WaitlistRead]:
        """Everyone still waiting or already notified, oldest first — the order they joined the queue."""
        entries = self.db.scalars(
            select(WaitlistEntry).where(
                WaitlistEntry.restaurant_id == restaurant_id,
                WaitlistEntry.status.in_([WaitlistStatus.WAITING, WaitlistStatus.NOTIFIED]),
            ).order_by(WaitlistEntry.created_at)
        ).all()
        return [self._to_read(e) for e in entries]

    def notify(self, entry_id: int, restaurant_id: int) -> WaitlistRead:
        restaurant = self._active_restaurant(restaurant_id)
        entry = self._get(entry_id, restaurant_id)
        if entry.status != WaitlistStatus.WAITING:
            raise AppError("Only a waiting guest can be notified")
        entry.status = WaitlistStatus.NOTIFIED
        entry.notified_at = _utcnow()
        notify_waitlist_ready(self.db, restaurant, entry)
        self.db.commit()
        self.db.refresh(entry)
        return self._to_read(entry)

    def seat(self, entry_id: int, restaurant_id: int, data: WaitlistSeat) -> WaitlistRead:
        entry = self._get(entry_id, restaurant_id)
        if entry.status not in (WaitlistStatus.WAITING, WaitlistStatus.NOTIFIED):
            raise AppError("This guest is no longer waiting")
        reservation = self.reservations.create_admin_reservation(
            restaurant_id,
            AdminReservationCreate(
                table_id=data.table_id, party_size=entry.party_size, starts_at=_utcnow(),
                duration_minutes=data.duration_minutes, guest_name=entry.guest_name,
                guest_email=entry.guest_email, guest_phone=entry.guest_phone, notes=entry.notes,
                seat_immediately=True,
            ),
        )
        entry.status = WaitlistStatus.SEATED
        entry.reservation_id = reservation.id
        self.db.commit()
        self.db.refresh(entry)
        return self._to_read(entry)

    def cancel(self, entry_id: int, restaurant_id: int) -> WaitlistRead:
        entry = self._get(entry_id, restaurant_id)
        if entry.status not in (WaitlistStatus.WAITING, WaitlistStatus.NOTIFIED):
            raise AppError("This guest is no longer waiting")
        entry.status = WaitlistStatus.CANCELLED
        entry.cancelled_at = _utcnow()
        self.db.commit()
        self.db.refresh(entry)
        return self._to_read(entry)
