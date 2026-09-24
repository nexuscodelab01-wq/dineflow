"""Loyalty points: a running balance per customer, plus the ledger of what changed it."""

from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import LoyaltyReason
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.order import Order
    from app.models.restaurant import Restaurant
    from app.models.user import User


class LoyaltyAccount(TimestampMixin, Base):
    """One row per (restaurant, customer) — the balance is denormalized here so reading it is cheap;
    `LoyaltyTransaction` is the source of truth for how it got there."""

    __tablename__ = "loyalty_accounts"
    __table_args__ = (UniqueConstraint("restaurant_id", "user_id", name="uq_loyalty_accounts_user"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(
        ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    balance: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    restaurant: Mapped["Restaurant"] = relationship("Restaurant")
    user: Mapped["User"] = relationship("User")


class LoyaltyTransaction(TimestampMixin, Base):
    __tablename__ = "loyalty_transactions"
    __table_args__ = (
        # One earn transaction per order — the guard against double-crediting a re-notified status change.
        UniqueConstraint("order_id", name="uq_loyalty_transactions_order"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(
        ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id", ondelete="SET NULL"), nullable=True)
    points: Mapped[int] = mapped_column(Integer, nullable=False)  # positive to earn, negative to redeem/deduct
    reason: Mapped[LoyaltyReason] = mapped_column(Enum(LoyaltyReason, name="loyalty_reason"), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(200), nullable=True)  # staff name, for an ADJUSTED row

    restaurant: Mapped["Restaurant"] = relationship("Restaurant")
    user: Mapped["User"] = relationship("User")
    order: Mapped["Order | None"] = relationship("Order")
