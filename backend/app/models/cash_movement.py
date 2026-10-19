"""A cash-drawer adjustment with no order behind it — topping up the float, paying a delivery driver's
tip out in cash, and so on. Immutable once recorded, like AuditLog (own created_at, no updated_at)."""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import CashMovementKind

if TYPE_CHECKING:
    from app.models.shift import Shift
    from app.models.user import User


class CashMovement(Base):
    __tablename__ = "cash_movements"

    id: Mapped[int] = mapped_column(primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True)
    shift_id: Mapped[int] = mapped_column(ForeignKey("shifts.id", ondelete="CASCADE"), nullable=False, index=True)
    kind: Mapped[CashMovementKind] = mapped_column(Enum(CashMovementKind, name="cash_movement_kind"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)  # always positive; direction is `kind`
    reason: Mapped[str] = mapped_column(String(300), nullable=False)
    staff_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    shift: Mapped["Shift"] = relationship("Shift")
    staff: Mapped["User | None"] = relationship("User")
