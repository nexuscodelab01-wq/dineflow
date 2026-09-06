"""Analytics response schemas."""

from decimal import Decimal

from pydantic import BaseModel

from app.models.enums import OrderStatus
from app.schemas.admin import DashboardStats


class TimeSeriesPoint(BaseModel):
    date: str
    orders: int = 0
    revenue: Decimal = Decimal("0.00")


class CategoryBreakdown(BaseModel):
    category_name: str
    order_count: int
    revenue: Decimal


class PopularItem(BaseModel):
    item_name: str
    quantity: int
    revenue: Decimal


class StatusBreakdown(BaseModel):
    status: OrderStatus
    count: int


class AnalyticsResponse(BaseModel):
    preset: str
    start_date: str
    end_date: str
    summary: DashboardStats
    revenue_over_time: list[TimeSeriesPoint]
    orders_over_time: list[TimeSeriesPoint]
    orders_by_category: list[CategoryBreakdown]
    popular_items: list[PopularItem]
    order_status_distribution: list[StatusBreakdown]
