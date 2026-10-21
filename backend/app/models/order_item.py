"""Order line item ORM model."""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.menu_item import MenuItem
    from app.models.order import Order
    from app.models.order_item_modifier import OrderItemModifier


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    menu_item_id: Mapped[int] = mapped_column(
        ForeignKey("menu_items.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    item_name: Mapped[str] = mapped_column(String(200), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    special_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Copied from the dish when ordered, so changing a dish's station later doesn't move tickets already on a screen.
    station: Mapped[str] = mapped_column(String(20), default="KITCHEN", server_default="KITCHEN", nullable=False)
    # Also copied at order time, same reasoning as `station`: the kitchen ticket must show what the
    # dish contained *when ordered*, not whatever the menu says now.
    allergens: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="'[]'::jsonb", nullable=False)
    # NEW until its station bumps it, then READY. Recall puts it back to NEW.
    # Snapshots, like `station`: what this line was taxed as, and the tax charged on it, when ordered.
    tax_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Manual discount / comp already taken off this line (line_total is the net after it).
    # Course firing: items past course 1 are held (kept off the kitchen screen) until staff fire that course.
    course: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    held: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    # The (split) payment that paid for this line — set when a guest pays "just my items" from a shared tab.
    paid_payment_id: Mapped[int | None] = mapped_column(ForeignKey("payments.id", ondelete="SET NULL"), nullable=True)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"), server_default="0.00", nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"), server_default="0", nullable=False)
    status: Mapped[str] = mapped_column(String(10), default="NEW", server_default="NEW", nullable=False)
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    order: Mapped["Order"] = relationship("Order", back_populates="items")
    menu_item: Mapped["MenuItem"] = relationship("MenuItem")
    modifiers: Mapped[list["OrderItemModifier"]] = relationship(
        "OrderItemModifier", back_populates="order_item", cascade="all, delete-orphan"
    )
