"""Restaurant Pydantic schemas."""

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
    address: str | None = None
    city: str | None = None
    postal_code: str | None = None
    phone: str | None = None
    email: str | None = None
    opening_hours: dict[str, Any] | None = None
    delivery_enabled: bool
    pickup_enabled: bool
    dine_in_enabled: bool
    tax_rate: Decimal
    delivery_fee: Decimal
    is_active: bool
