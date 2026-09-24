"""Restaurant ORM model."""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, DateTime, Index, Integer, Numeric, String, Text
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
    __table_args__ = (Index("uq_restaurants_custom_domain", "custom_domain", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Brand colour as #rrggbb; the site derives its whole palette from it (when the custom_branding flag is on).
    primary_color: Mapped[str | None] = mapped_column(String(7), nullable=True)
    # Accent colour for badges, highlights and secondary buttons; optional — falls back to the primary palette.
    secondary_color: Mapped[str | None] = mapped_column(String(7), nullable=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    opening_hours: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    # IANA name (e.g. "America/Los_Angeles"); a restaurant with no opening_hours is always open regardless.
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", server_default="UTC", nullable=False)
    # Whole extra days closed beyond the weekly hours: [{"date": "2026-12-25", "label": "Christmas"}].
    closures: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, server_default="'[]'::jsonb", nullable=False)
    delivery_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    pickup_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    dine_in_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("0.0825"), nullable=False)
    delivery_fee: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("4.99"), nullable=False)
    reservation_buffer_minutes: Mapped[int] = mapped_column(
        Integer, default=15, server_default="15", nullable=False
    )
    # Own domain for this restaurant's site (e.g. order.bellavista.com); resolves to this tenant.
    custom_domain: Mapped[str | None] = mapped_column(String(253), nullable=True)
    # Set by a platform admin's "Verify domain" action. A stand-in for real DNS/TLS automation (Stage E);
    # not enforced anywhere yet, just shown as a status.
    domain_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Order numbers are "<prefix>-<n>", counted per restaurant.
    order_prefix: Mapped[str] = mapped_column(String(8), default="DF", server_default="DF", nullable=False)
    next_order_number: Mapped[int] = mapped_column(Integer, default=1001, server_default="1001", nullable=False)
    # Who may open a table's QR menu: SEATED (only while the table is occupied) or OPEN (any time).
    qr_access_policy: Mapped[str] = mapped_column(String(10), default="SEATED", server_default="SEATED", nullable=False)
    # Guest booking limits, enforced on customer-facing availability/booking only — staff can always
    # override for private events or corrections. max_party_size null = no upper limit.
    min_party_size: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    max_party_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # How much notice a guest must give before a booking's start time.
    booking_lead_time_minutes: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    # Pacing: the most guests (summed party sizes) who may book into the same 15-minute arrival slot.
    # Null = no cap. Independent of table availability — protects the kitchen from an arrival flood
    # even when there happen to be enough free tables.
    max_covers_per_slot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Longer-form story for the home page's "About us" section — `description` stays the short
    # tagline shown in the hero and menu page.
    about_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Photo gallery for the home page: an ordered list of uploaded/linked image URLs.
    gallery: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="'[]'::jsonb", nullable=False)
    # {"instagram": "https://...", "facebook": "https://...", ...} — every key optional.
    social_links: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict, server_default="'{}'::jsonb", nullable=False)
    # Optional map coordinates for the home page. Null = no embedded map, just the address text.
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    # Whole loyalty points earned per whole currency unit spent on a completed order (floor of total * rate).
    loyalty_points_per_currency: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
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
