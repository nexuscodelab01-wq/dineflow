"""Restaurant Pydantic schemas."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict


class RestaurantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
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
    timezone: str = "UTC"
    closures: list[dict[str, Any]] = []
    delivery_enabled: bool
    pickup_enabled: bool
    dine_in_enabled: bool
    tax_rate: Decimal
    delivery_fee: Decimal
    reservation_buffer_minutes: int = 15
    min_party_size: int = 1
    max_party_size: int | None = None
    booking_lead_time_minutes: int = 0
    custom_domain: str | None = None
    domain_verified_at: datetime | None = None
    is_active: bool


class TenantRead(RestaurantRead):
    """What a restaurant's own site needs on load: its details plus which features are switched on."""

    features: dict[str, bool] = {}


class TenantCreateResponse(BaseModel):
    restaurant_id: int
    name: str
    slug: str
    order_prefix: str
    owner_email: str
    site_url: str
    # A one-time set-password link (shown once — the platform admin passes it to the owner).
    invite_link: str | None = None
