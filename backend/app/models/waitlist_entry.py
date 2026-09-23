"""Walk-in waitlist ORM model — a queue for guests with no table free yet."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import WaitlistStatus
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.reservation import Reservation
    from app.models.restaurant import Restaurant


class WaitlistEntry(TimestampMixin, Base):
    __tablename__ = "waitlist_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(
        ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    guest_name: Mapped[str] = mapped_column(String(200), nullable=False)
    guest_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    guest_phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    party_size: Mapped[int] = mapped_column(Integer, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # A staff-entered guess ("about 20 minutes"), shown to the guest and on the board — not enforced.
    quoted_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[WaitlistStatus] = mapped_column(
        Enum(WaitlistStatus, name="waitlist_status"), default=WaitlistStatus.WAITING, nullable=False, index=True
    )
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Set once seated: the walk-in becomes a normal SEATED reservation, so the table, kitchen and
    # floor-plan machinery all just work the same way they do for any other walk-in.
    reservation_id: Mapped[int | None] = mapped_column(
        ForeignKey("reservations.id", ondelete="SET NULL"), nullable=True
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    restaurant: Mapped["Restaurant"] = relationship("Restaurant")
    reservation: Mapped["Reservation | None"] = relationship("Reservation")
