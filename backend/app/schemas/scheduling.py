"""Scheduled-order (collection slot) Pydantic schemas."""

from datetime import datetime

from pydantic import BaseModel


class PickupSlot(BaseModel):
    at: datetime
    remaining: int | None  # None = no per-slot cap set


class PickupSlotsResponse(BaseModel):
    date: str          # the local date these slots belong to
    timezone: str      # the restaurant's own zone, so a client can label the times correctly
    days_ahead: int    # how far ahead this restaurant takes pre-orders
    interval_minutes: int
    slots: list[PickupSlot]
