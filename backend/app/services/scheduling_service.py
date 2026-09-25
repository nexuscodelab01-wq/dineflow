"""Ordering capacity: whether an order can be taken now, and which later collection slots are free.

Two separate jobs that both answer "can we take this order?":

* **Capacity** — a restaurant can pause online ordering outright, or have it pause itself once the
  kitchen has `max_pending_orders` tickets still open. Staff putting an order in for a guest are not
  affected; this only guards the customer-facing path.
* **Scheduling** — collection slots are generated from the restaurant's own opening hours, so there
  is one source of truth for when it's open (`app/core/hours.py`).

A slot the client asks for is always re-checked here against a freshly generated grid, so a stale
page or a hand-made request can't book a slot that is closed, full or in the past.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.core.hours import local_now, slots_for_day, to_local
from app.models.enums import OrderStatus
from app.models.order import Order
from app.models.restaurant import Restaurant

# Orders that no longer occupy a slot or the kitchen queue.
_DONE_STATUSES = (OrderStatus.CANCELLED, OrderStatus.COMPLETED, OrderStatus.DELIVERED)


@dataclass
class Slot:
    at: datetime          # aware, in the restaurant's own zone
    remaining: int | None  # None = no cap on this slot


class SchedulingService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------ capacity

    def ensure_accepting_orders(self, restaurant: Restaurant, *, scheduled: bool = False) -> None:
        """Raises when a customer's order must be turned away. Staff paths don't call this.

        A pause stops everything, pre-orders included — "stop taking orders" should mean that. The
        busy cap is about the queue right now, so an order for a later slot is not held against it.
        """
        if restaurant.online_ordering_paused:
            reason = restaurant.ordering_pause_reason or "we've paused online orders for a moment"
            raise AppError(f"{restaurant.name} isn't taking online orders right now — {reason}.")
        if not scheduled and restaurant.max_pending_orders is not None:
            pending = self.db.scalar(
                select(func.count(Order.id)).where(
                    Order.restaurant_id == restaurant.id,
                    Order.status.not_in(_DONE_STATUSES),
                    # A scheduled order isn't in the queue yet, so it doesn't count towards being busy.
                    Order.scheduled_for.is_(None),
                )
            ) or 0
            if pending >= restaurant.max_pending_orders:
                raise AppError(
                    f"{restaurant.name}'s kitchen is at capacity right now. Please try again in a few minutes."
                )

    # ------------------------------------------------------------------ slots

    def _taken_per_slot(self, restaurant_id: int, start: datetime, end: datetime) -> dict[datetime, int]:
        rows = self.db.execute(
            select(Order.scheduled_for, func.count(Order.id))
            .where(
                Order.restaurant_id == restaurant_id,
                Order.scheduled_for.is_not(None),
                Order.scheduled_for >= start,
                Order.scheduled_for < end,
                Order.status.not_in((OrderStatus.CANCELLED,)),
            )
            .group_by(Order.scheduled_for)
        ).all()
        return {at: count for at, count in rows}

    def available_slots(self, restaurant: Restaurant, on: date, *, now: datetime | None = None) -> list[Slot]:
        """Bookable collection times on `on`. Empty when that day is closed, fully booked or too far off."""
        current = to_local(restaurant, now) if now else local_now(restaurant)
        today = current.date()
        if on < today or on > today + timedelta(days=restaurant.scheduled_order_days_ahead):
            return []

        grid = slots_for_day(restaurant, on, restaurant.slot_interval_minutes)
        if not grid:
            return []

        # Nothing sooner than the kitchen's lead time — a 10-minute-away slot is no use if it takes 30.
        earliest = current + timedelta(minutes=restaurant.scheduled_order_lead_minutes)
        taken = self._taken_per_slot(restaurant.id, grid[0], grid[-1] + timedelta(minutes=restaurant.slot_interval_minutes))
        cap = restaurant.max_orders_per_slot

        slots: list[Slot] = []
        for at in grid:
            if at < earliest:
                continue
            if cap is None:
                slots.append(Slot(at=at, remaining=None))
                continue
            remaining = cap - taken.get(at, 0)
            if remaining > 0:
                slots.append(Slot(at=at, remaining=remaining))
        return slots

    def validate_scheduled_for(self, restaurant: Restaurant, requested: datetime, *, now: datetime | None = None) -> datetime:
        """The requested slot, or an AppError saying why not. Matched against a freshly built grid."""
        if requested.tzinfo is None:
            raise AppError("A collection time must include its timezone")
        local = to_local(restaurant, requested)
        for slot in self.available_slots(restaurant, local.date(), now=now):
            if slot.at == local:
                return requested
        raise AppError("That collection time isn't available any more. Please pick another slot.")
