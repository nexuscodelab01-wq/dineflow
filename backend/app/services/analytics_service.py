"""Analytics business logic."""

import csv
import io
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.repositories.analytics import AnalyticsRepository
from app.schemas.admin import DashboardStats
from app.schemas.analytics import (
    AnalyticsResponse,
    CategoryBreakdown,
    HourlyBreakdown,
    NoShowStats,
    PopularItem,
    StatusBreakdown,
    TimeSeriesPoint,
)
from app.schemas.time_entry import EmployeeReportRow
from app.services.time_entry_service import TimeEntryService
from app.services.tip_service import TipService
from app.utils.date_ranges import DateRangePreset, resolve_date_range


class AnalyticsService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.analytics = AnalyticsRepository(db)
        self.time_entries = TimeEntryService(db)

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
            sales_by_hour=[HourlyBreakdown(**row) for row in self.analytics.sales_by_hour(restaurant_id, start, end)],
            no_show=NoShowStats(**self.analytics.no_show_stats(restaurant_id, start, end)),
        )

    def employee_report(
        self,
        restaurant_id: int,
        preset: DateRangePreset,
        *,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[EmployeeReportRow]:
        try:
            start, end = resolve_date_range(preset, start_date=start_date, end_date=end_date)
        except ValueError as exc:
            raise AppError(str(exc)) from exc

        totals = self.analytics.employee_totals(restaurant_id, start, end)
        hours = self.time_entries.hours_worked(restaurant_id, start, end)
        tips = TipService(self.db)
        card_tips = tips.card_tips(restaurant_id, start, end)
        cash_tips = tips.cash_tips(restaurant_id, start, end)

        rows = []
        for row in totals:
            hours_worked = hours.get(row["user_id"], Decimal("0.00"))
            takings = row["cash_total"] + row["card_total"]
            sales_per_labour_hour = (takings / hours_worked).quantize(Decimal("0.01")) if hours_worked > 0 else None
            rows.append(EmployeeReportRow(
                user_id=row["user_id"], name=row["name"], cash_total=row["cash_total"],
                card_total=row["card_total"], order_count=row["order_count"],
                hours_worked=hours_worked, sales_per_labour_hour=sales_per_labour_hour,
                card_tips=card_tips.get(row["user_id"], Decimal("0.00")), cash_tips=cash_tips.get(row["user_id"], Decimal("0.00")),
            ))
        return rows

    def export_orders_csv(
        self,
        restaurant_id: int,
        preset: DateRangePreset,
        *,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> str:
        try:
            start, end = resolve_date_range(preset, start_date=start_date, end_date=end_date)
        except ValueError as exc:
            raise AppError(str(exc)) from exc

        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow([
            "order_number", "created_at", "status", "order_type", "customer_name", "customer_email",
            "subtotal", "tax", "delivery_fee", "discount", "total",
        ])
        for order in self.analytics.orders_for_export(restaurant_id, start, end):
            writer.writerow([
                order.order_number, order.created_at.isoformat(), order.status.value, order.order_type.value,
                order.customer_name, order.customer_email or "",
                order.subtotal, order.tax, order.delivery_fee, order.discount, order.total,
            ])
        return buffer.getvalue()
