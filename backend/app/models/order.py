"""Order ORM model."""

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import OrderStatus, OrderType
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.address import Address
    from app.models.order_item import OrderItem
    from app.models.order_status_history import OrderStatusHistory
    from app.models.payment import Payment
    from app.models.reservation import Reservation
    from app.models.restaurant import Restaurant
    from app.models.restaurant_table import RestaurantTable
    from app.models.user import User


class Order(TimestampMixin, Base):
    __tablename__ = "orders"
    __table_args__ = (UniqueConstraint("restaurant_id", "order_number", name="uq_orders_restaurant_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    restaurant_id: Mapped[int] = mapped_column(
        ForeignKey("restaurants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    order_number: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    order_type: Mapped[OrderType] = mapped_column(Enum(OrderType, name="order_type"), nullable=False)
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus, name="order_status"), default=OrderStatus.PENDING, nullable=False, index=True
    )
    subtotal: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    tax: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    delivery_fee: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"), nullable=False)
    discount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"), nullable=False)
    total: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    customer_name: Mapped[str] = mapped_column(String(200), nullable=False)
    customer_email: Mapped[str] = mapped_column(String(255), nullable=False)
    customer_phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    delivery_address_id: Mapped[int | None] = mapped_column(
        ForeignKey("addresses.id", ondelete="SET NULL"), nullable=True
    )
    table_id: Mapped[int | None] = mapped_column(
        ForeignKey("restaurant_tables.id", ondelete="SET NULL"), nullable=True
    )
    delivery_instructions: Mapped[str | None] = mapped_column(String(500), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    @property
    def table_number(self) -> str | None:
        """The table's name for dine-in orders (what the kitchen calls out)."""
        return self.table.table_number if self.table is not None else None

    user: Mapped["User | None"] = relationship("User", back_populates="orders")
    restaurant: Mapped["Restaurant"] = relationship("Restaurant", back_populates="orders")
    delivery_address: Mapped["Address | None"] = relationship("Address", back_populates="orders")
    table: Mapped["RestaurantTable | None"] = relationship("RestaurantTable", back_populates="orders")
    items: Mapped[list["OrderItem"]] = relationship(
        "OrderItem", back_populates="order", cascade="all, delete-orphan"
    )
    payments: Mapped[list["Payment"]] = relationship(
        "Payment", back_populates="order", cascade="all, delete-orphan"
    )
    status_history: Mapped[list["OrderStatusHistory"]] = relationship(
        "OrderStatusHistory", back_populates="order", cascade="all, delete-orphan"
    )
    reservation: Mapped["Reservation | None"] = relationship(
        "Reservation",
        back_populates="order",
        uselist=False,
        foreign_keys="Reservation.order_id",
    )
