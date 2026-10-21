"""Clock in/out — an employee's working hours, scoped to the person, not a till.

Deliberately simple: one open entry per person at a time, no breaks, no edits/approval workflow (a
manager who needs to fix a forgotten clock-out has no tool for that yet — a documented limitation, not
silently worked around). `hours_worked` is read-time-computed from closed entries only; an entry still
open when a report runs is excluded from that row's total (the hours aren't final yet, not a bug).
"""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AppError, ConflictError
from app.models.enums import PaymentMethod, PaymentStatus
from app.models.payment import Payment
from app.models.time_entry import TimeEntry
from app.models.user import User
from app.schemas.time_entry import TimeEntryRead
from app.schemas.tips import CashUpRequest
from app.services.feature_service import FeatureService

FEATURE = "pos"


class TimeEntryService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def current_entry(self, restaurant_id: int, user: User) -> TimeEntryRead | None:
        entry = self._open_entry(restaurant_id, user.id)
        return self._read(entry) if entry else None

    def clock_in(self, restaurant_id: int, user: User, device_id: int | None) -> TimeEntryRead:
        FeatureService(self.db).require(restaurant_id, FEATURE)
        if self._open_entry(restaurant_id, user.id) is not None:
            raise ConflictError("Already clocked in")
        try:
            with self.db.begin_nested():
                entry = TimeEntry(restaurant_id=restaurant_id, user_id=user.id, clock_in_device_id=device_id)
                self.db.add(entry)
                self.db.flush()
        except IntegrityError:  # two near-simultaneous clock-ins for the same person
            raise ConflictError("Already clocked in") from None
        self.db.commit()
        return self._read(entry)

    def clock_out(self, restaurant_id: int, user: User, cash_up: CashUpRequest | None = None) -> TimeEntryRead:
        entry = self._open_entry(restaurant_id, user.id)
        if entry is None:
            raise AppError("Not clocked in")
        entry.clock_out_at = datetime.now(UTC)
        if cash_up is not None:
            entry.counted_cash = cash_up.counted_cash
            entry.cash_tips = cash_up.cash_tips
        self.db.commit()
        return self._read(entry)

    def hours_worked(self, restaurant_id: int, start: datetime, end: datetime) -> dict[int, Decimal]:
        """Per-user_id total hours worked, clamped to [start, end] at each end, from closed entries that
        overlap the range at all."""
        entries = self.db.scalars(
            select(TimeEntry).where(
                TimeEntry.restaurant_id == restaurant_id,
                TimeEntry.clock_out_at.is_not(None),
                TimeEntry.clock_in_at < end,
                TimeEntry.clock_out_at > start,
            )
        ).all()
        totals: dict[int, Decimal] = {}
        for entry in entries:
            assert entry.clock_out_at is not None  # guaranteed by the filter above
            clamped_start = max(entry.clock_in_at, start)
            clamped_end = min(entry.clock_out_at, end)
            hours = Decimal((clamped_end - clamped_start).total_seconds()) / Decimal(3600)
            totals[entry.user_id] = totals.get(entry.user_id, Decimal("0.00")) + hours
        return {user_id: hours.quantize(Decimal("0.01")) for user_id, hours in totals.items()}

    def _open_entry(self, restaurant_id: int, user_id: int) -> TimeEntry | None:
        return self.db.scalar(select(TimeEntry).where(
            TimeEntry.restaurant_id == restaurant_id, TimeEntry.user_id == user_id, TimeEntry.clock_out_at.is_(None),
        ))

    def _read(self, entry: TimeEntry) -> TimeEntryRead:
        until = entry.clock_out_at or datetime.now(UTC)
        expected = self.db.scalar(select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.restaurant_id == entry.restaurant_id, Payment.staff_user_id == entry.user_id,
            Payment.status == PaymentStatus.COMPLETED, Payment.payment_method == PaymentMethod.CASH,
            Payment.created_at >= entry.clock_in_at, Payment.created_at <= until,
        )) or Decimal("0.00")
        expected = Decimal(expected)
        variance = (entry.counted_cash - entry.cash_tips - expected) if entry.counted_cash is not None else None
        return TimeEntryRead(
            id=entry.id, clock_in_at=entry.clock_in_at, clock_out_at=entry.clock_out_at, counted_cash=entry.counted_cash,
            cash_tips=entry.cash_tips, expected_cash=expected, variance=variance,
        )
