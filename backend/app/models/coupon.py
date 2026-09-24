"""Discount coupons and the ledger of who redeemed what.

The coupon only ever describes the *rule*; the money is worked out server-side at order time
(`CouponService.compute_discount`). A client never sends an amount — see OrderCreate.
"""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import CouponDiscountType
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.order import Order
    from app.models.restaurant import Restaurant
    from app.models.user import User


class Coupon(TimestampMixin, Base):
    __tablename__ = "coupons"
    __table_args__ = (
        # Codes are compared case-insensitively by storing them upper-cased, so "SAVE10" and "save10"
        # are the same coupon and can't both be created.
        UniqueConstraint("restaurant_id", "code", name="uq_coupons_restaurant_code"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(
        ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String(200), nullable=True)
    discount_type: Mapped[CouponDiscountType] = mapped_column(
        Enum(CouponDiscountType, name="coupon_discount_type"), nullable=False
    )
    discount_value: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    # Rules, all optional. Null means "no limit".
    min_order_amount: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    max_discount_amount: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)  # caps a PERCENT coupon
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    max_redemptions: Mapped[int | None] = mapped_column(Integer, nullable=True)       # across everyone
    max_per_customer: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Denormalized count of the rows in `coupon_redemptions`; kept in step under a row lock so a
    # "first 100 customers" coupon can't overshoot when two people check out at the same moment.
    times_redeemed: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    restaurant: Mapped["Restaurant"] = relationship("Restaurant")
    redemptions: Mapped[list["CouponRedemption"]] = relationship(
        "CouponRedemption", back_populates="coupon", cascade="all, delete-orphan"
    )


class CouponRedemption(TimestampMixin, Base):
    __tablename__ = "coupon_redemptions"
    __table_args__ = (
        # One coupon per order, enforced by the database rather than by hoping the service is careful.
        UniqueConstraint("order_id", name="uq_coupon_redemptions_order"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(
        ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    coupon_id: Mapped[int] = mapped_column(ForeignKey("coupons.id", ondelete="CASCADE"), nullable=False, index=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)  # what it actually took off

    coupon: Mapped["Coupon"] = relationship("Coupon", back_populates="redemptions")
    order: Mapped["Order"] = relationship("Order")
    user: Mapped["User | None"] = relationship("User")
