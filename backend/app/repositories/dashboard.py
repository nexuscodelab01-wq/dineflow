"""Admin dashboard data access."""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.enums import OrderStatus, PaymentStatus
from app.models.order import Order
from app.models.payment import Payment


class DashboardRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def stats(self, restaurant_id: int) -> dict[str, Decimal | int]:
        """A cancelled order never happened, so it counts toward none of these — same rule as
        AnalyticsRepository (see its docstring)."""
        today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        not_cancelled = Order.status != OrderStatus.CANCELLED

        today_orders = self.db.scalar(
            select(func.count(Order.id)).where(
                Order.restaurant_id == restaurant_id,
                Order.created_at >= today_start,
                not_cancelled,
            )
        ) or 0

        # Filtered on Payment's own restaurant_id/created_at, not joined through Order — a table-session
        # payment (pay at table) has no order_id to join through. An order-payment is still excluded
        # when its order was cancelled (the outer join keeps a table-session payment either way, since
        # it has no matching order at all). See AnalyticsRepository._revenue, same reasoning.
        now = datetime.now(UTC)
        today_revenue = self.db.scalar(
            select(func.coalesce(func.sum(Payment.amount), 0))
            .select_from(Payment)
            .outerjoin(Order, Payment.order_id == Order.id)
            .where(
                Payment.restaurant_id == restaurant_id,
                Payment.created_at >= today_start,
                Payment.created_at <= now,
                Payment.status == PaymentStatus.COMPLETED,
                or_(Payment.order_id.is_(None), Order.status != OrderStatus.CANCELLED),
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
