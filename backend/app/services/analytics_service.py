"""Analytics business logic."""

from datetime import datetime

from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.repositories.analytics import AnalyticsRepository
from app.schemas.admin import DashboardStats
from app.schemas.analytics import (
    AnalyticsResponse,
    CategoryBreakdown,
    PopularItem,
    StatusBreakdown,
    TimeSeriesPoint,
)
from app.utils.date_ranges import DateRangePreset, resolve_date_range


class AnalyticsService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.analytics = AnalyticsRepository(db)

    def get_analytics(
        self,
        restaurant_id: int,
        preset: DateRangePreset,
        *,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> AnalyticsResponse:
        try:
            start, end = resolve_date_range(preset, start_date=start_date, end_date=end_date)
        except ValueError as exc:
            raise AppError(str(exc)) from exc

        series = self.analytics.time_series(restaurant_id, start, end)
        summary = self.analytics.summary(restaurant_id, start, end)

        return AnalyticsResponse(
            preset=preset.value,
            start_date=start.date().isoformat(),
            end_date=end.date().isoformat(),
            summary=DashboardStats(**summary),
            revenue_over_time=[TimeSeriesPoint(**p) for p in series],
            orders_over_time=[TimeSeriesPoint(**p) for p in series],
            orders_by_category=[
                CategoryBreakdown(**row)
                for row in self.analytics.orders_by_category(restaurant_id, start, end)
            ],
            popular_items=[
                PopularItem(**row)
                for row in self.analytics.popular_items(restaurant_id, start, end)
            ],
            order_status_distribution=[
                StatusBreakdown(status=row["status"], count=row["count"])
                for row in self.analytics.status_distribution(restaurant_id, start, end)
            ],
        )
