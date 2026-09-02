"""Order data access."""

import math

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.order import Order
from app.models.order_item import OrderItem


class OrderRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, order_id: int) -> Order | None:
        stmt = (
            select(Order)
            .options(
                selectinload(Order.items).selectinload(OrderItem.modifiers),
                selectinload(Order.status_history),
                selectinload(Order.payments),
            )
            .where(Order.id == order_id)
        )
        return self.db.scalar(stmt)

    def get_by_id_for_user(self, order_id: int, user_id: int) -> Order | None:
        order = self.get_by_id(order_id)
        if order and order.user_id == user_id:
            return order
        return None

    def list_for_user(
        self,
        user_id: int,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Order], int]:
        base = select(Order).where(Order.user_id == user_id)
        total = self.db.scalar(select(func.count()).select_from(base.subquery())) or 0
        stmt = (
            base.options(
                selectinload(Order.items).selectinload(OrderItem.modifiers),
                selectinload(Order.status_history),
                selectinload(Order.payments),
            )
            .order_by(Order.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = list(self.db.scalars(stmt).unique().all())
        return items, total

    @staticmethod
    def pages(total: int, page_size: int) -> int:
        return max(1, math.ceil(total / page_size)) if total else 1

    def add(self, order: Order) -> Order:
        self.db.add(order)
        self.db.flush()
        return order
