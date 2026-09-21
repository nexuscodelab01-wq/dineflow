"""Menu Pydantic schemas."""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class CategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    description: str | None = None
    sort_order: int
    is_active: bool


class ModifierOptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    price_adjustment: Decimal
    is_default: bool
    sort_order: int


class MenuModifierRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None
    is_required: bool
    min_selections: int
    max_selections: int
    sort_order: int
    options: list[ModifierOptionRead] = Field(default_factory=list)


class MenuItemListRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    restaurant_id: int
    category_id: int
    category_name: str | None = None
    name: str
    description: str | None = None
    price: Decimal
    image_url: str | None = None
    is_available: bool
    preparation_time_minutes: int
    is_vegetarian: bool
    is_spicy: bool
    is_popular: bool
    station: str = "KITCHEN"


class MenuItemDetailRead(MenuItemListRead):
    modifiers: list[MenuModifierRead] = Field(default_factory=list)


class MenuListResponse(BaseModel):
    items: list[MenuItemListRead]
    total: int
    page: int
    page_size: int
    pages: int
