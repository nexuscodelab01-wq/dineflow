"""Restaurant ORM model."""

from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.category import Category
    from app.models.menu_item import MenuItem
    from app.models.menu_modifier import MenuModifier
    from app.models.order import Order
    from app.models.reservation import Reservation
    from app.models.restaurant_table import RestaurantTable
    from app.models.restaurant_user import RestaurantUser


class Restaurant(TimestampMixin, Base):
    __tablename__ = "restaurants"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    opening_hours: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    delivery_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    pickup_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    dine_in_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("0.0825"), nullable=False)
    delivery_fee: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("4.99"), nullable=False)
    reservation_buffer_minutes: Mapped[int] = mapped_column(
        Integer, default=15, server_default="15", nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    staff: Mapped[list["RestaurantUser"]] = relationship(
        "RestaurantUser", back_populates="restaurant", cascade="all, delete-orphan"
    )
    categories: Mapped[list["Category"]] = relationship(
        "Category", back_populates="restaurant", cascade="all, delete-orphan"
    )
    menu_items: Mapped[list["MenuItem"]] = relationship(
        "MenuItem", back_populates="restaurant", cascade="all, delete-orphan"
    )
    modifiers: Mapped[list["MenuModifier"]] = relationship(
        "MenuModifier", back_populates="restaurant", cascade="all, delete-orphan"
    )
    tables: Mapped[list["RestaurantTable"]] = relationship(
        "RestaurantTable", back_populates="restaurant", cascade="all, delete-orphan"
    )
    orders: Mapped[list["Order"]] = relationship("Order", back_populates="restaurant")
    reservations: Mapped[list["Reservation"]] = relationship(
        "Reservation", back_populates="restaurant", cascade="all, delete-orphan"
    )
