"""Every void, comp, manual discount and refund taken at the POS — who did it, who approved it, why, and on
which till shift — so money that left the building is always explainable (and shows up in the Z-report)."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

VOID = "VOID"
COMP = "COMP"
DISCOUNT = "DISCOUNT"
REFUND = "REFUND"
KINDS = (VOID, COMP, DISCOUNT, REFUND)


class OrderAdjustment(Base):
    __tablename__ = "order_adjustments"

    id: Mapped[int] = mapped_column(primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id", ondelete="SET NULL"), nullable=True, index=True)
    table_session_id: Mapped[int | None] = mapped_column(ForeignKey("table_sessions.id", ondelete="SET NULL"), nullable=True, index=True)
    # The line affected, if any. SET NULL because a voided line is deleted — `detail` keeps its snapshot.
    order_item_id: Mapped[int | None] = mapped_column(ForeignKey("order_items.id", ondelete="SET NULL"), nullable=True)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)  # money taken off / given back (positive)
    reason_code: Mapped[str] = mapped_column(String(30), nullable=False)
    note: Mapped[str | None] = mapped_column(String(300), nullable=True)
    staff_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    authorized_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    shift_id: Mapped[int | None] = mapped_column(ForeignKey("shifts.id", ondelete="SET NULL"), nullable=True, index=True)
    # Refunds only: how it was paid and which shift took the payment, so the Z-report can tell whether the
    # cash left THIS drawer (payment from an earlier shift) or simply netted out within it.
    payment_method: Mapped[str | None] = mapped_column(String(10), nullable=True)
    original_shift_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
