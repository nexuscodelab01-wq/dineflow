"""Analytics data access."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.category import Category
from app.models.enums import OrderStatus, PaymentStatus
from app.models.menu_item import MenuItem
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.payment import Payment


class AnalyticsRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def _order_filter(self, restaurant_id: int, start: datetime, end: datetime):
        return (
            Order.restaurant_id == restaurant_id,
            Order.created_at >= start,
            Order.created_at <= end,
        )

    def summary(self, restaurant_id: int, start: datetime, end: datetime) -> dict:
        filters = self._order_filter(restaurant_id, start, end)

        total_orders = self.db.scalar(
            select(func.count(Order.id)).where(*filters)
        ) or 0

        revenue = self.db.scalar(
            select(func.coalesce(func.sum(Payment.amount), 0))
            .join(Order, Payment.order_id == Order.id)
            .where(
                *filters,
                Payment.status == PaymentStatus.COMPLETED,
            )
        ) or Decimal("0.00")

        pending = self.db.scalar(
            select(func.count(Order.id)).where(
                Order.restaurant_id == restaurant_id,
                Order.status.in_([
                    OrderStatus.PENDING,
                    OrderStatus.CONFIRMED,
                    OrderStatus.PREPARING,
                    OrderStatus.READY,
                    OrderStatus.OUT_FOR_DELIVERY,
                ]),
                Order.created_at >= start,
                Order.created_at <= end,
            )
        ) or 0

        completed = self.db.scalar(
            select(func.count(Order.id)).where(
                *filters,
                Order.status.in_([OrderStatus.COMPLETED, OrderStatus.DELIVERED]),
            )
        ) or 0

        avg = Decimal("0.00")
        if total_orders:
            avg = (Decimal(revenue) / total_orders).quantize(Decimal("0.01"))

        return {
            "today_orders": total_orders,
            "today_revenue": Decimal(revenue).quantize(Decimal("0.01")),
            "pending_orders": pending,
            "completed_orders_today": completed,
            "average_order_value": avg,
        }

    def time_series(self, restaurant_id: int, start: datetime, end: datetime) -> list[dict]:
        day = start
        points: list[dict] = []
        while day.date() <= end.date():
            day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day.replace(hour=23, minute=59, second=59, microsecond=999999)
            if day_end.tzinfo is None:
                day_end = day_end.replace(tzinfo=UTC)

            orders = self.db.scalar(
                select(func.count(Order.id)).where(
                    Order.restaurant_id == restaurant_id,
                    Order.created_at >= day_start,
                    Order.created_at <= day_end,
                )
            ) or 0

            revenue = self.db.scalar(
                select(func.coalesce(func.sum(Payment.amount), 0))
                .join(Order, Payment.order_id == Order.id)
                .where(
                    Order.restaurant_id == restaurant_id,
                    Order.created_at >= day_start,
                    Order.created_at <= day_end,
                    Payment.status == PaymentStatus.COMPLETED,
                )
            ) or Decimal("0.00")

            points.append({
                "date": day_start.date().isoformat(),
                "orders": orders,
                "revenue": Decimal(revenue).quantize(Decimal("0.01")),
            })
            day += timedelta(days=1)
        return points

    def orders_by_category(self, restaurant_id: int, start: datetime, end: datetime) -> list[dict]:
        stmt = (
            select(
                Category.name,
                func.count(func.distinct(Order.id)).label("order_count"),
                func.coalesce(func.sum(OrderItem.line_total), 0).label("revenue"),
            )
            .join(MenuItem, MenuItem.category_id == Category.id)
            .join(OrderItem, OrderItem.menu_item_id == MenuItem.id)
            .join(Order, Order.id == OrderItem.order_id)
            .where(
                Order.restaurant_id == restaurant_id,
                Category.restaurant_id == restaurant_id,
                Order.created_at >= start,
                Order.created_at <= end,
            )
            .group_by(Category.name)
            .order_by(func.sum(OrderItem.line_total).desc())
        )
        rows = self.db.execute(stmt).all()
        return [
            {
                "category_name": row.name,
                "order_count": row.order_count,
                "revenue": Decimal(row.revenue).quantize(Decimal("0.01")),
            }
            for row in rows
        ]

    def popular_items(self, restaurant_id: int, start: datetime, end: datetime, limit: int = 10) -> list[dict]:
        stmt = (
            select(
                OrderItem.item_name,
                func.sum(OrderItem.quantity).label("quantity"),
                func.sum(OrderItem.line_total).label("revenue"),
            )
            .join(Order, Order.id == OrderItem.order_id)
            .where(
                Order.restaurant_id == restaurant_id,
                Order.created_at >= start,
                Order.created_at <= end,
            )
            .group_by(OrderItem.item_name)
            .order_by(func.sum(OrderItem.quantity).desc())
            .limit(limit)
        )
        rows = self.db.execute(stmt).all()
        return [
            {
                "item_name": row.item_name,
                "quantity": int(row.quantity),
                "revenue": Decimal(row.revenue).quantize(Decimal("0.01")),
            }
            for row in rows
        ]

    def status_distribution(self, restaurant_id: int, start: datetime, end: datetime) -> list[dict]:
        stmt = (
            select(Order.status, func.count(Order.id))
            .where(
                Order.restaurant_id == restaurant_id,
                Order.created_at >= start,
                Order.created_at <= end,
            )
            .group_by(Order.status)
        )
        rows = self.db.execute(stmt).all()
        return [{"status": row[0], "count": row[1]} for row in rows]
