"""Admin request/response schemas."""

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import OrderStatus, OrderType, TableStatus
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
    is_available: bool = True
    preparation_time_minutes: int = Field(default=15, ge=1)
    is_vegetarian: bool = False
    is_spicy: bool = False
    is_popular: bool = False
    sort_order: int = 0
    modifier_ids: list[int] = Field(default_factory=list)


class MenuItemUpdate(BaseModel):
    category_id: int | None = None
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    price: Decimal | None = Field(default=None, gt=0)
    image_url: str | None = None
    is_available: bool | None = None
    preparation_time_minutes: int | None = Field(default=None, ge=1)
    is_vegetarian: bool | None = None
    is_spicy: bool | None = None
    is_popular: bool | None = None
    sort_order: int | None = None
    modifier_ids: list[int] | None = None


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


class OrderStatusUpdate(BaseModel):
    status: OrderStatus
    notes: str | None = Field(default=None, max_length=500)


class AdminOrderFilters(BaseModel):
    status: OrderStatus | None = None
    order_type: OrderType | None = None
    search: str | None = None
    page: int = 1
    page_size: int = 20


class TableCreate(BaseModel):
    restaurant_id: int
    table_number: str = Field(min_length=1, max_length=20)
    capacity: int = Field(ge=1, le=20)
    status: TableStatus = TableStatus.AVAILABLE


class TableUpdate(BaseModel):
    table_number: str | None = Field(default=None, min_length=1, max_length=20)
    capacity: int | None = Field(default=None, ge=1, le=20)


class TableStatusUpdate(BaseModel):
    status: TableStatus
    # Must be true to release/clean a table that still has an active or imminent reservation.
    force: bool = False


class TableRead(BaseModel):
    id: int
    table_number: str
    capacity: int
    status: TableStatus
    reservations: list[TableReservationBrief] = Field(default_factory=list)


class RestaurantSettingsUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    logo_url: str | None = None
    address: str | None = None
    city: str | None = None
    postal_code: str | None = None
    phone: str | None = None
    email: str | None = None
    opening_hours: dict[str, Any] | None = None
    delivery_enabled: bool | None = None
    pickup_enabled: bool | None = None
    dine_in_enabled: bool | None = None
    tax_rate: Decimal | None = Field(default=None, ge=0, le=1)
    delivery_fee: Decimal | None = Field(default=None, ge=0)
    reservation_buffer_minutes: int | None = Field(default=None, ge=0, le=60)


class CustomerSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    first_name: str
    last_name: str
    phone: str | None = None
    is_active: bool
    total_orders: int
    total_spending: Decimal
    last_order_at: str | None = None


class KitchenBoard(BaseModel):
    new_orders: list[OrderRead]
    preparing: list[OrderRead]
    ready: list[OrderRead]
