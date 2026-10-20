"""An employee's clock in/out record — scoped to the person, not a till. Unlike `Shift` (one open shift
per Device), an employee's working hours are about them, not which iPad they happened to use: they can
clock in on one device and clock out on another. One row per stretch of work, mutated twice (clock-in,
then clock-out) — the same lifecycle shape `Shift` uses, not `CashMovement`'s single logged event.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.device import Device
    from app.models.user import User


class TimeEntry(Base):
    __tablename__ = "time_entries"
    __table_args__ = (
        # At most one open entry per person at a time — race-proof at the DB level, same template as
        # Shift.uq_shifts_one_open_per_device.
        Index(
            "uq_time_entries_one_open_per_user", "restaurant_id", "user_id", unique=True,
            postgresql_where=text("clock_out_at IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    clock_in_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    # Informational only (which till they happened to clock in from) — never used to scope anything.
    clock_in_device_id: Mapped[int | None] = mapped_column(ForeignKey("devices.id", ondelete="SET NULL"), nullable=True)
    clock_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship("User")
    clock_in_device: Mapped["Device | None"] = relationship("Device")
