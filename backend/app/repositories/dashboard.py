"""Admin dashboard data access."""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.enums import OrderStatus, PaymentStatus
from app.models.order import Order
from app.models.payment import Payment


class DashboardRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def stats(self, restaurant_id: int) -> dict[str, Decimal | int]:
        today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)

        today_orders = self.db.scalar(
            select(func.count(Order.id)).where(
                Order.restaurant_id == restaurant_id,
                Order.created_at >= today_start,
            )
        ) or 0

        today_revenue = self.db.scalar(
            select(func.coalesce(func.sum(Payment.amount), 0))
            .join(Order, Payment.order_id == Order.id)
            .where(
                Order.restaurant_id == restaurant_id,
                Order.created_at >= today_start,
                Payment.status == PaymentStatus.COMPLETED,
            )
        ) or Decimal("0.00")

        pending_orders = self.db.scalar(
            select(func.count(Order.id)).where(
                Order.restaurant_id == restaurant_id,
                Order.status.in_([
                    OrderStatus.PENDING,
                    OrderStatus.CONFIRMED,
                    OrderStatus.PREPARING,
                    OrderStatus.READY,
                    OrderStatus.OUT_FOR_DELIVERY,
                ]),
            )
        ) or 0

        completed_today = self.db.scalar(
            select(func.count(Order.id)).where(
                Order.restaurant_id == restaurant_id,
                Order.created_at >= today_start,
                Order.status.in_([OrderStatus.COMPLETED, OrderStatus.DELIVERED]),
            )
        ) or 0

        avg_order_value = Decimal("0.00")
        if today_orders:
            avg_order_value = (Decimal(today_revenue) / today_orders).quantize(Decimal("0.01"))

        return {
            "today_orders": today_orders,
            "today_revenue": Decimal(today_revenue).quantize(Decimal("0.01")),
            "pending_orders": pending_orders,
            "completed_orders_today": completed_today,
            "average_order_value": avg_order_value,
        }
