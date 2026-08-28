"""Restaurant staff membership ORM model."""

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.restaurant import Restaurant
    from app.models.user import User


class RestaurantUser(Base):
    __tablename__ = "restaurant_users"
    __table_args__ = (UniqueConstraint("restaurant_id", "user_id", name="uq_restaurant_user"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(
        ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    restaurant: Mapped["Restaurant"] = relationship("Restaurant", back_populates="staff")
    user: Mapped["User"] = relationship("User", back_populates="restaurant_memberships")
