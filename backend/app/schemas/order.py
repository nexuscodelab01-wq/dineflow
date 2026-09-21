"""Order Pydantic schemas."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.enums import OrderStatus, OrderType, PaymentMethod, PaymentStatus


class DeliveryAddressCreate(BaseModel):
    street: str = Field(min_length=1, max_length=255)
    city: str = Field(min_length=1, max_length=100)
    postal_code: str = Field(min_length=1, max_length=20)
    delivery_instructions: str | None = Field(default=None, max_length=500)


class OrderItemCreate(BaseModel):
    menu_item_id: int
    quantity: int = Field(ge=1, le=50)
    modifier_option_ids: list[int] = Field(default_factory=list)
    special_instructions: str | None = Field(default=None, max_length=500)


class OrderCreate(BaseModel):
    restaurant_id: int
    order_type: OrderType
    items: list[OrderItemCreate] = Field(min_length=1)
    customer_name: str = Field(min_length=1, max_length=200)
    customer_email: EmailStr
    customer_phone: str | None = Field(default=None, max_length=30)
    # Prices, discounts and the table are decided by the server — never by the client.
    # (Unknown fields such as `discount` or `table_id` in a request are ignored.)
    reservation_id: int | None = None
    delivery_address: DeliveryAddressCreate | None = None
    delivery_instructions: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=1000)


class OrderItemModifierRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    modifier_name: str
    option_name: str
    price_adjustment: Decimal


class OrderItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    menu_item_id: int
    item_name: str
    quantity: int
    unit_price: Decimal
    line_total: Decimal
    special_instructions: str | None = None
    station: str = "KITCHEN"
    status: str = "NEW"
    ready_at: datetime | None = None
    modifiers: list[OrderItemModifierRead] = Field(default_factory=list)


class OrderStatusHistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    previous_status: OrderStatus | None = None
    new_status: OrderStatus
    created_at: datetime


class PaymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    amount: Decimal
    status: PaymentStatus
    payment_method: PaymentMethod


class OrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_number: str
    restaurant_id: int
    order_type: OrderType
    table_number: str | None = None
    status: OrderStatus
    subtotal: Decimal
    tax: Decimal
    delivery_fee: Decimal
    discount: Decimal
    total: Decimal
    customer_name: str
    customer_email: EmailStr | None = None
    customer_phone: str | None = None
    delivery_instructions: str | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime
    items: list[OrderItemRead] = Field(default_factory=list)
    status_history: list[OrderStatusHistoryRead] = Field(default_factory=list)
    payments: list[PaymentRead] = Field(default_factory=list)


class OrderListResponse(BaseModel):
    items: list[OrderRead]
    total: int
    page: int
    page_size: int
    pages: int
