"""A device's till session: opened with a starting cash float, closed with a counted-cash recap.

Scoped to one physical Device, not one staff member — multiple staff can PIN-switch during one open
shift (see app/services/shift_service.py's module docstring for why, and for the expected-cash math).
`expected_cash`/`variance`/totals are derived at read time from Payment/CashMovement rows, never stored
here — only what was actually entered (starting_float, counted_cash) lives on this row.
"""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.device import Device
    from app.models.user import User

OPEN = "OPEN"
CLOSED = "CLOSED"


class Shift(Base):
    __tablename__ = "shifts"
    __table_args__ = (
        # A device has at most one open shift at any time — race-proof at the DB level, same template
        # as TableSession.uq_table_sessions_one_open.
        Index("uq_shifts_one_open_per_device", "device_id", unique=True, postgresql_where=text("state = 'OPEN'")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True)
    state: Mapped[str] = mapped_column(String(10), default=OPEN, server_default=OPEN, nullable=False)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    opened_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    starting_float: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    counted_cash: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)  # set on close
    # Cash tips the closer declared (they sit in the drawer but belong to staff, not the house).
    cash_tips: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"), server_default="0.00", nullable=False)

    device: Mapped["Device"] = relationship("Device")
    opened_by: Mapped["User | None"] = relationship("User", foreign_keys=[opened_by_user_id])
    closed_by: Mapped["User | None"] = relationship("User", foreign_keys=[closed_by_user_id])
