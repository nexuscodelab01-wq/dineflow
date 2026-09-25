"""Admin request/response schemas."""

import re
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.config import settings
from app.core.hours import InvalidHours, validate_closures, validate_opening_hours, valid_timezone
from app.core.stations import STATIONS
from app.models.enums import OrderStatus, OrderType, TableShape, TableStatus
from app.schemas.menu import CategoryRead, MenuItemDetailRead, MenuModifierRead
from app.schemas.order import OrderRead
from app.schemas.reservation import TableReservationBrief
from app.schemas.restaurant import RestaurantRead


class DashboardStats(BaseModel):
    today_orders: int
    today_revenue: Decimal
    pending_orders: int
    completed_orders_today: int
    average_order_value: Decimal


class CategoryCreate(BaseModel):
    restaurant_id: int
    name: str = Field(min_length=1, max_length=100)
    slug: str = Field(min_length=1, max_length=100)
    description: str | None = None
    sort_order: int = 0
    is_active: bool = True


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    slug: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None
    sort_order: int | None = None
    is_active: bool | None = None


class CategoryReorderItem(BaseModel):
    id: int
    sort_order: int


class CategoryReorder(BaseModel):
    items: list[CategoryReorderItem]


class MenuItemCreate(BaseModel):
    restaurant_id: int
    category_id: int
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    price: Decimal = Field(gt=0)
    image_url: str | None = None

    @field_validator("image_url")
    @classmethod
    def _check_image_url(cls, value: str | None) -> str | None:
        return _media_url(value)
    station: str = "KITCHEN"
    is_available: bool = True
    preparation_time_minutes: int = Field(default=15, ge=1)
    is_vegetarian: bool = False
    is_spicy: bool = False
    is_popular: bool = False
    sort_order: int = 0
    modifier_ids: list[int] = Field(default_factory=list)

    @field_validator("station")
    @classmethod
    def _station(cls, value: str) -> str:
        return _check_station(value)


def _check_station(value):
    if value is not None and value not in STATIONS:
        raise ValueError(f"Station must be one of: {', '.join(STATIONS)}")
    return value


class MenuItemUpdate(BaseModel):
    category_id: int | None = None
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    price: Decimal | None = Field(default=None, gt=0)
    image_url: str | None = None

    @field_validator("image_url")
    @classmethod
    def _check_image_url(cls, value: str | None) -> str | None:
        return _media_url(value)
    station: str | None = None
    is_available: bool | None = None
    preparation_time_minutes: int | None = Field(default=None, ge=1)
    is_vegetarian: bool | None = None
    is_spicy: bool | None = None
    is_popular: bool | None = None
    sort_order: int | None = None
    modifier_ids: list[int] | None = None

    @field_validator("station")
    @classmethod
    def _station(cls, value: str | None) -> str | None:
        return _check_station(value)


class ModifierOptionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    price_adjustment: Decimal = Decimal("0.00")
    is_default: bool = False
    sort_order: int = 0


class ModifierOptionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    price_adjustment: Decimal | None = None
    is_default: bool | None = None
    sort_order: int | None = None


class MenuModifierCreate(BaseModel):
    restaurant_id: int
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    is_required: bool = False
    min_selections: int = 0
    max_selections: int = 1
    sort_order: int = 0
    options: list[ModifierOptionCreate] = Field(default_factory=list)


class MenuModifierUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None
    is_required: bool | None = None
    min_selections: int | None = None
    max_selections: int | None = None
    sort_order: int | None = None


class SoldOutUpdate(BaseModel):
    sold_out: bool


class OrderStatusUpdate(BaseModel):
    status: OrderStatus
    notes: str | None = Field(default=None, max_length=500)


class AdminOrderFilters(BaseModel):
    status: OrderStatus | None = None
    order_type: OrderType | None = None
    search: str | None = None
    page: int = 1
    page_size: int = 20


def _media_url(value: str | None) -> str | None:
    """An image field may hold an uploaded path (/uploads/…) or an http(s) URL — nothing else."""
    value = (value or "").strip()
    if not value:
        return None
    if len(value) > 500 or any(ch.isspace() or ord(ch) < 32 for ch in value):
        raise ValueError("Image address is invalid")
    if not (value.startswith("/uploads/") or value.startswith(("https://", "http://"))):
        raise ValueError("Image must be an uploaded file or an http(s) link")
    return value


def _clean_zone(value: str | None) -> str | None:
    value = (value or "").strip()
    return value or None


class TableCreate(BaseModel):
    restaurant_id: int
    table_number: str = Field(min_length=1, max_length=20)
    capacity: int = Field(ge=1, le=20)
    zone: str | None = Field(default=None, max_length=50)
    shape: TableShape = TableShape.SQUARE
    pos_x: float | None = Field(default=None, ge=0, le=100)
    pos_y: float | None = Field(default=None, ge=0, le=100)

    @field_validator("table_number")
    @classmethod
    def _strip_number(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Table name can't be blank")
        return value

    @field_validator("zone")
    @classmethod
    def _strip_zone(cls, value: str | None) -> str | None:
        return _clean_zone(value)


class TableUpdate(BaseModel):
    table_number: str | None = Field(default=None, min_length=1, max_length=20)
    capacity: int | None = Field(default=None, ge=1, le=20)
    zone: str | None = Field(default=None, max_length=50)  # send null to clear
    shape: TableShape | None = None
    pos_x: float | None = Field(default=None, ge=0, le=100)
    pos_y: float | None = Field(default=None, ge=0, le=100)
    is_active: bool | None = None

    @field_validator("table_number")
    @classmethod
    def _strip_number(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("Table name can't be blank")
        return value

    @field_validator("zone")
    @classmethod
    def _strip_zone(cls, value: str | None) -> str | None:
        return _clean_zone(value)


class TableLayoutItem(BaseModel):
    id: int
    pos_x: float = Field(ge=0, le=100)
    pos_y: float = Field(ge=0, le=100)


class TableLayoutUpdate(BaseModel):
    """Positions for many tables at once (saving a floor-plan drag session)."""

    items: list[TableLayoutItem] = Field(min_length=1)


class TableStatusUpdate(BaseModel):
    status: TableStatus
    # Must be true to release/clean a table that still has an active or imminent reservation.
    force: bool = False


class TableRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    table_number: str
    capacity: int
    status: TableStatus
    zone: str | None = None
    shape: str = "SQUARE"
    pos_x: float | None = None
    pos_y: float | None = None
    is_active: bool = True
    reservations: list[TableReservationBrief] = Field(default_factory=list)


class RestaurantSettingsUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    logo_url: str | None = None
    primary_color: str | None = None
    secondary_color: str | None = None
    address: str | None = None
    city: str | None = None
    postal_code: str | None = None
    phone: str | None = None
    email: str | None = None
    opening_hours: dict[str, Any] | None = None
    timezone: str | None = None
    closures: list[dict[str, Any]] | None = None
    custom_domain: str | None = None
    delivery_enabled: bool | None = None
    pickup_enabled: bool | None = None
    dine_in_enabled: bool | None = None
    tax_rate: Decimal | None = Field(default=None, ge=0, le=1)
    delivery_fee: Decimal | None = Field(default=None, ge=0)
    reservation_buffer_minutes: int | None = Field(default=None, ge=0, le=60)
    # Guest booking policy — staff can still book outside these limits for private events or corrections.
    # Capped at 20 to match the hard ceiling on party_size for an online booking (ReservationCreate).
    min_party_size: int | None = Field(default=None, ge=1, le=20)
    max_party_size: int | None = Field(default=None, ge=1, le=20)
    booking_lead_time_minutes: int | None = Field(default=None, ge=0, le=10080)  # up to a week's notice
    max_covers_per_slot: int | None = Field(default=None, ge=1, le=1000)
    # Home page content.
    about_text: str | None = Field(default=None, max_length=4000)
    gallery: list[str] | None = Field(default=None, max_length=20)
    social_links: dict[str, str] | None = None
    latitude: Decimal | None = Field(default=None, ge=-90, le=90)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180)
    loyalty_points_per_currency: int | None = Field(default=None, ge=0, le=1000)
    # Ordering capacity and scheduled collection slots.
    online_ordering_paused: bool | None = None
    ordering_pause_reason: str | None = Field(default=None, max_length=200)
    max_pending_orders: int | None = Field(default=None, ge=1, le=500)
    slot_interval_minutes: int | None = Field(default=None, ge=5, le=120)
    max_orders_per_slot: int | None = Field(default=None, ge=1, le=100)
    scheduled_order_days_ahead: int | None = Field(default=None, ge=0, le=60)
    scheduled_order_lead_minutes: int | None = Field(default=None, ge=0, le=480)

    @field_validator("logo_url")
    @classmethod
    def _check_logo_url(cls, value: str | None) -> str | None:
        return _media_url(value)

    @field_validator("about_text")
    @classmethod
    def _check_about_text(cls, value: str | None) -> str | None:
        value = (value or "").strip()
        return value or None

    @field_validator("gallery")
    @classmethod
    def _check_gallery(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        cleaned = [_media_url(v) for v in value]
        return [v for v in cleaned if v]

    @field_validator("social_links")
    @classmethod
    def _check_social_links(cls, value: dict[str, str] | None) -> dict[str, str] | None:
        if value is None:
            return None
        allowed = {"instagram", "facebook", "twitter", "tiktok", "youtube"}
        cleaned: dict[str, str] = {}
        for key, url in value.items():
            if key not in allowed:
                raise ValueError(f"Unknown social link '{key}' — allowed: {', '.join(sorted(allowed))}")
            url = (url or "").strip()
            if not url:
                continue
            if len(url) > 500 or not url.startswith(("https://", "http://")):
                raise ValueError(f"{key} link must be a full http(s) URL")
            cleaned[key] = url
        return cleaned

    @field_validator("opening_hours")
    @classmethod
    def _check_opening_hours(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is None:
            return None
        try:
            validate_opening_hours(value)
        except InvalidHours as exc:
            raise ValueError(str(exc)) from exc
        return value

    @field_validator("timezone")
    @classmethod
    def _check_timezone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not valid_timezone(value):
            raise ValueError(f"'{value}' is not a known timezone (e.g. 'America/Los_Angeles', 'Europe/London', 'UTC')")
        return value

    @field_validator("closures")
    @classmethod
    def _check_closures(cls, value: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
        if value is None:
            return None
        try:
            validate_closures(value)
        except InvalidHours as exc:
            raise ValueError(str(exc)) from exc
        return value

    @field_validator("custom_domain")
    @classmethod
    def _check_custom_domain(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        value = value.strip().lower()
        if not re.fullmatch(r"(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}", value):
            raise ValueError("That doesn't look like a domain, e.g. order.yourrestaurant.com")
        platform_domain = settings.PLATFORM_DOMAIN.lower() if settings.PLATFORM_DOMAIN else None
        is_platform_subdomain = platform_domain is not None and (value == platform_domain or value.endswith(f".{platform_domain}"))
        if value in settings.reserved_subdomains or is_platform_subdomain:
            raise ValueError("Use a domain you own, not a subdomain of the platform's own domain")
        return value

    @field_validator("primary_color", "secondary_color")
    @classmethod
    def _check_primary_color(cls, value: str | None) -> str | None:
        # Injected into a <style> tag by the site, so it must be exactly #rrggbb and nothing else.
        # An empty string means "cleared" (e.g. an unfilled colour picker) same as custom_domain above.
        if value is None or value == "":
            return None
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
            raise ValueError("Colour must look like #1a7f5a")
        return value.lower()


class CustomerSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    first_name: str
    last_name: str
    phone: str | None = None
    is_active: bool
    is_vip: bool = False
    notes: str | None = None
    allergies: str | None = None
    total_orders: int
    total_spending: Decimal
    last_order_at: str | None = None
    total_bookings: int = 0
    # The more recent of their last order and last booking — "have we seen them lately", not just "have they ordered".
    last_seen_at: str | None = None


class CustomerProfileUpdate(BaseModel):
    notes: str | None = Field(default=None, max_length=4000)
    allergies: str | None = Field(default=None, max_length=1000)
    is_vip: bool | None = None


class CustomerReservationBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    starts_at: datetime
    party_size: int
    status: str
    table_number: str | None = None

    @field_validator("status", mode="before")
    @classmethod
    def _status_value(cls, value):
        return value.value if hasattr(value, "value") else value


class CustomerDetail(BaseModel):
    id: int
    email: str
    first_name: str
    last_name: str
    phone: str | None = None
    is_active: bool
    is_vip: bool
    notes: str | None = None
    allergies: str | None = None
    total_orders: int
    total_spending: Decimal
    total_bookings: int
    orders: list[OrderRead]
    reservations: list[CustomerReservationBrief]


class KitchenBoard(BaseModel):
    new_orders: list[OrderRead]
    preparing: list[OrderRead]
    ready: list[OrderRead]
