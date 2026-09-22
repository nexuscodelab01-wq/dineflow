"""User ORM model."""

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.address import Address
    from app.models.order import Order
    from app.models.refresh_token import RefreshToken
    from app.models.reservation import Reservation
    from app.models.restaurant_user import RestaurantUser
    from app.models.role import Role


class User(TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        # A customer's email is unique within their restaurant; global identities (staff, platform
        # admins) are unique among themselves. The same email can therefore be a customer of two
        # restaurants without the accounts being linked.
        Index("uq_users_tenant_email", "restaurant_id", "email", unique=True, postgresql_where=text("restaurant_id IS NOT NULL")),
        Index("uq_users_global_email", "email", unique=True, postgresql_where=text("restaurant_id IS NULL")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), nullable=False, index=True)
    # The restaurant (tenant) a CUSTOMER belongs to. NULL for global identities: restaurant staff and
    # platform admins, who reach restaurants through RestaurantUser memberships.
    restaurant_id: Mapped[int | None] = mapped_column(
        ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=True, index=True
    )
    # Guest-profile notes a restaurant keeps on its own customer (only meaningful for CUSTOMER rows).
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    allergies: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_vip: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)

    role: Mapped["Role"] = relationship("Role", back_populates="users")
    restaurant_memberships: Mapped[list["RestaurantUser"]] = relationship(
        "RestaurantUser", back_populates="user", cascade="all, delete-orphan"
    )
    orders: Mapped[list["Order"]] = relationship("Order", back_populates="user")
    reservations: Mapped[list["Reservation"]] = relationship("Reservation", back_populates="user")
    addresses: Mapped[list["Address"]] = relationship(
        "Address", back_populates="user", cascade="all, delete-orphan"
    )
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        "RefreshToken", back_populates="user", cascade="all, delete-orphan"
    )

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()
