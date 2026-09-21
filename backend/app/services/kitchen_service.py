"""The kitchen screen's actions: bump or recall dishes, and take a dish off the menu (86) live."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import AppError, NotFoundError
from app.core.realtime import kitchen_topic, publish, publish_order_change
from app.core.stations import is_station
from app.models.enums import OrderStatus
from app.models.menu_item import MenuItem
from app.models.order import Order
from app.models.order_item import OrderItem
from app.repositories.admin_order import AdminOrderRepository

NEW, READY = "NEW", "READY"
ACTIVE = (OrderStatus.CONFIRMED, OrderStatus.PREPARING, OrderStatus.READY)


class KitchenService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.orders = AdminOrderRepository(db)

    # ------------------------------------------------------------------ dishes

    def bump_item(self, item_id: int, restaurant_id: int, user_id: int | None) -> None:
        """This dish is done. When every dish on the ticket is done the order becomes READY."""
        item, order = self._item(item_id, restaurant_id)
        if item.status != READY:
            item.status, item.ready_at = READY, datetime.now(UTC)
        self._settle(order, user_id)
        self.db.commit()

    def recall_item(self, item_id: int, restaurant_id: int, user_id: int | None) -> None:
        """Undo a bump (it was pressed by mistake, or the dish went back). A READY order returns to PREPARING."""
        item, order = self._item(item_id, restaurant_id)
        item.status, item.ready_at = NEW, None
        self._settle(order, user_id)
        self.db.commit()

    def bump_ticket(self, order_id: int, restaurant_id: int, station: str | None, user_id: int | None) -> None:
        """Bump every open dish of one ticket, or only this station's dishes."""
        if station is not None and not is_station(station):
            raise AppError("Unknown station")
        order = self._order(order_id, restaurant_id)
        now = datetime.now(UTC)
        for item in order.items:
            if item.status != READY and (station is None or item.station == station):
                item.status, item.ready_at = READY, now
        self._settle(order, user_id)
        self.db.commit()

    def _settle(self, order: Order, user_id: int | None) -> None:
        """Keep the order's own status in step with its dishes, and tell everyone who is watching."""
        previous = order.status
        items = order.items
        all_ready = bool(items) and all(i.status == READY for i in items)
        any_ready = any(i.status == READY for i in items)
        if all_ready:
            target = OrderStatus.READY
        elif any_ready or previous == OrderStatus.PREPARING:
            target = OrderStatus.PREPARING
        else:
            target = OrderStatus.CONFIRMED if previous == OrderStatus.CONFIRMED else OrderStatus.PREPARING
        if target != previous:
            order.status = target
            self.orders.add_status_history(order=order, previous=previous, new=target, user_id=user_id, notes="From the kitchen screen")
            publish(self.db, kitchen_topic(order.restaurant_id), "order.status", {"order_id": order.id, "status": target.value})
            publish_order_change(self.db, order, "order.status", {"status": target.value})
        else:
            publish(self.db, kitchen_topic(order.restaurant_id), "ticket.updated", {"order_id": order.id})

    # ------------------------------------------------------------------ 86

    def set_sold_out(self, menu_item_id: int, restaurant_id: int, sold_out: bool) -> MenuItem:
        """Take a dish off (or put it back on) every menu and QR ordering at once."""
        item = self.db.get(MenuItem, menu_item_id)
        if item is None or item.restaurant_id != restaurant_id:
            raise NotFoundError("Menu item not found")
        item.is_available = not sold_out
        publish(self.db, kitchen_topic(restaurant_id), "menu.changed", {"menu_item_id": item.id, "is_available": item.is_available})
        self.db.commit()
        return item

    # ------------------------------------------------------------------ lookups

    def _order(self, order_id: int, restaurant_id: int) -> Order:
        order = self.db.scalar(
            select(Order).options(selectinload(Order.items)).where(Order.id == order_id, Order.restaurant_id == restaurant_id)
        )
        if order is None:
            raise NotFoundError("Order not found")
        if order.status not in ACTIVE:
            raise AppError("This order is no longer on the kitchen screen")
        return order

    def _item(self, item_id: int, restaurant_id: int) -> tuple[OrderItem, Order]:
        item = self.db.get(OrderItem, item_id)
        if item is None:
            raise NotFoundError("Order item not found")
        return item, self._order(item.order_id, restaurant_id)
