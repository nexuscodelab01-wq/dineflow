"""Admin order and table data access."""

import math
from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.enums import OrderStatus, OrderType
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.order_status_history import OrderStatusHistory
from app.models.reservation import Reservation
from app.models.restaurant_table import RestaurantTable
from app.models.user import User


class AdminOrderRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_for_restaurant(
        self,
        restaurant_id: int,
        *,
        status: OrderStatus | None = None,
        order_type: OrderType | None = None,
        search: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Order], int]:
        stmt = select(Order).where(Order.restaurant_id == restaurant_id)
        if status:
            stmt = stmt.where(Order.status == status)
        if order_type:
            stmt = stmt.where(Order.order_type == order_type)
        if search:
            pattern = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    Order.order_number.ilike(pattern),
                    Order.customer_name.ilike(pattern),
                    Order.customer_email.ilike(pattern),
                )
            )

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = self.db.scalar(count_stmt) or 0

        stmt = (
            stmt.options(
                selectinload(Order.items).selectinload(OrderItem.modifiers),
                selectinload(Order.status_history),
                selectinload(Order.payments),
                joinedload(Order.table),
            )
            .order_by(Order.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(self.db.scalars(stmt).unique().all()), total

    def get_for_restaurant(self, order_id: int, restaurant_id: int) -> Order | None:
        stmt = (
            select(Order)
            .options(
                selectinload(Order.items).selectinload(OrderItem.modifiers),
                selectinload(Order.status_history),
                selectinload(Order.payments),
                joinedload(Order.table),
            )
            .where(Order.id == order_id, Order.restaurant_id == restaurant_id)
        )
        return self.db.scalar(stmt)

    def kitchen_orders(self, restaurant_id: int) -> dict[str, list[Order]]:
        active_statuses = [
            OrderStatus.CONFIRMED,
            OrderStatus.PREPARING,
            OrderStatus.READY,
        ]
        stmt = (
            select(Order)
            .options(selectinload(Order.items).selectinload(OrderItem.modifiers), joinedload(Order.table))
            .where(Order.restaurant_id == restaurant_id, Order.status.in_(active_statuses))
            .order_by(Order.created_at.asc())
        )
        orders = list(self.db.scalars(stmt).unique().all())
        return {
            "new_orders": [o for o in orders if o.status == OrderStatus.CONFIRMED],
            "preparing": [o for o in orders if o.status == OrderStatus.PREPARING],
            "ready": [o for o in orders if o.status == OrderStatus.READY],
        }

    def add_status_history(
        self,
        *,
        order: Order,
        previous: OrderStatus | None,
        new: OrderStatus,
        user_id: int | None,
        notes: str | None = None,
    ) -> None:
        self.db.add(
            OrderStatusHistory(
                order_id=order.id,
                previous_status=previous,
                new_status=new,
                changed_by_user_id=user_id,
                notes=notes,
            )
        )

    @staticmethod
    def pages(total: int, page_size: int) -> int:
        return max(1, math.ceil(total / page_size)) if total else 1


class TableRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_for_restaurant(self, restaurant_id: int) -> list[RestaurantTable]:
        stmt = (
            select(RestaurantTable)
            .where(RestaurantTable.restaurant_id == restaurant_id)
            .order_by(RestaurantTable.table_number)
        )
        return list(self.db.scalars(stmt).all())

    def get_by_id(self, table_id: int) -> RestaurantTable | None:
        return self.db.get(RestaurantTable, table_id)

    def create(self, table: RestaurantTable) -> RestaurantTable:
        self.db.add(table)
        self.db.flush()
        return table

    def delete(self, table: RestaurantTable) -> None:
        self.db.delete(table)


class CustomerRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_for_restaurant(self, restaurant_id: int) -> list[dict]:
        """Every customer of this restaurant — including one who has only ever booked a table, or just signed
        up — not only those with an order (a plain join on Order used to make the rest invisible)."""
        order_stats = (
            select(
                Order.user_id.label("user_id"),
                func.count(Order.id).label("total_orders"),
                func.coalesce(func.sum(Order.total), 0).label("total_spending"),
                func.max(Order.created_at).label("last_order_at"),
            )
            .where(Order.restaurant_id == restaurant_id)
            .group_by(Order.user_id)
            .subquery()
        )
        booking_stats = (
            select(
                Reservation.user_id.label("user_id"),
                func.count(Reservation.id).label("total_bookings"),
                func.max(Reservation.starts_at).label("last_booking_at"),
            )
            .where(Reservation.restaurant_id == restaurant_id, Reservation.user_id.is_not(None))
            .group_by(Reservation.user_id)
            .subquery()
        )
        stmt = (
            select(
                User.id, User.email, User.first_name, User.last_name, User.phone, User.is_active,
                User.is_vip, User.notes, User.allergies,
                func.coalesce(order_stats.c.total_orders, 0).label("total_orders"),
                func.coalesce(order_stats.c.total_spending, 0).label("total_spending"),
                order_stats.c.last_order_at,
                func.coalesce(booking_stats.c.total_bookings, 0).label("total_bookings"),
                booking_stats.c.last_booking_at,
            )
            .outerjoin(order_stats, order_stats.c.user_id == User.id)
            .outerjoin(booking_stats, booking_stats.c.user_id == User.id)
            .where(User.restaurant_id == restaurant_id)  # only customers ever carry a restaurant_id
        )
        rows = self.db.execute(stmt).all()

        def last_seen(row) -> datetime | None:
            candidates = [d for d in (row.last_order_at, row.last_booking_at) if d is not None]
            return max(candidates) if candidates else None

        def to_dict(row) -> dict:
            seen = last_seen(row)
            return {
                "id": row.id, "email": row.email, "first_name": row.first_name, "last_name": row.last_name,
                "phone": row.phone, "is_active": row.is_active, "is_vip": row.is_vip,
                "notes": row.notes, "allergies": row.allergies,
                "total_orders": row.total_orders, "total_spending": row.total_spending,
                "total_bookings": row.total_bookings,
                "last_seen_at": seen.isoformat() if seen else None,
            }

        return sorted((to_dict(row) for row in rows), key=lambda c: c["last_seen_at"] or "", reverse=True)

    def get_for_restaurant(self, restaurant_id: int, user_id: int) -> User | None:
        return self.db.scalar(select(User).where(User.id == user_id, User.restaurant_id == restaurant_id))

    def get_customer_orders(self, restaurant_id: int, user_id: int) -> list[Order]:
        stmt = (
            select(Order)
            .options(selectinload(Order.items))
            .where(Order.restaurant_id == restaurant_id, Order.user_id == user_id)
            .order_by(Order.created_at.desc())
        )
        return list(self.db.scalars(stmt).unique().all())

    def get_customer_reservations(self, restaurant_id: int, user_id: int) -> list[Reservation]:
        stmt = (
            select(Reservation)
            .options(joinedload(Reservation.table))
            .where(Reservation.restaurant_id == restaurant_id, Reservation.user_id == user_id)
            .order_by(Reservation.starts_at.desc())
        )
        return list(self.db.scalars(stmt).unique().all())
