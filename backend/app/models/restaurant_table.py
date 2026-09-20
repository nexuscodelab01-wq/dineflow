"""Restaurant table ORM model."""

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Enum, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import TableStatus
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.order import Order
    from app.models.reservation import Reservation
    from app.models.restaurant import Restaurant


class RestaurantTable(TimestampMixin, Base):
    __tablename__ = "restaurant_tables"
    __table_args__ = (
        UniqueConstraint("restaurant_id", "table_number", name="uq_restaurant_table_number"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(
        ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    table_number: Mapped[str] = mapped_column(String(20), nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[TableStatus] = mapped_column(
        Enum(TableStatus, name="table_status"), default=TableStatus.AVAILABLE, nullable=False
    )
    # Seating area ("Window", "Bar", "Patio"…), free text so each restaurant names its own.
    zone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # ROUND | SQUARE | RECT — how the table is drawn on the floor plan.
    shape: Mapped[str] = mapped_column(String(10), default="SQUARE", server_default="SQUARE", nullable=False)
    # Floor-plan position as a percentage of the plan's width/height; NULL = not placed yet.
    pos_x: Mapped[float | None] = mapped_column(Float, nullable=True)
    pos_y: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Retired tables are hidden and can't be booked, but keep their reservation history.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)

    restaurant: Mapped["Restaurant"] = relationship("Restaurant", back_populates="tables")
    orders: Mapped[list["Order"]] = relationship("Order", back_populates="table")
    reservations: Mapped[list["Reservation"]] = relationship("Reservation", back_populates="table")
