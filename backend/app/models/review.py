"""Guest review ORM model — a rating + comment left after a completed order or reservation."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.order import Order
    from app.models.reservation import Reservation
    from app.models.restaurant import Restaurant
    from app.models.user import User


class Review(TimestampMixin, Base):
    __tablename__ = "reviews"
    __table_args__ = (
        CheckConstraint("rating >= 1 AND rating <= 5", name="ck_reviews_rating_range"),
        # Exactly one visit named — a review is always "about" one order or one reservation, never both.
        CheckConstraint(
            "(order_id IS NOT NULL)::int + (reservation_id IS NOT NULL)::int = 1",
            name="ck_reviews_one_visit",
        ),
        # One review per visit — resubmitting edits it instead (see ReviewService.upsert).
        UniqueConstraint("restaurant_id", "order_id", name="uq_reviews_order"),
        UniqueConstraint("restaurant_id", "reservation_id", name="uq_reviews_reservation"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(
        ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), nullable=True)
    reservation_id: Mapped[int | None] = mapped_column(
        ForeignKey("reservations.id", ondelete="CASCADE"), nullable=True
    )
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_published: Mapped[bool] = mapped_column(default=True, nullable=False)
    staff_reply: Mapped[str | None] = mapped_column(Text, nullable=True)
    staff_reply_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    restaurant: Mapped["Restaurant"] = relationship("Restaurant")
    user: Mapped["User"] = relationship("User")
    order: Mapped["Order | None"] = relationship("Order")
    reservation: Mapped["Reservation | None"] = relationship("Reservation")
