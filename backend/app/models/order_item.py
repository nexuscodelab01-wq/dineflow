"""Order line item ORM model."""

from decimal import Decimal
from typing import TYPE_CHECKING

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text
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
    # NEW until its station bumps it, then READY. Recall puts it back to NEW.
    status: Mapped[str] = mapped_column(String(10), default="NEW", server_default="NEW", nullable=False)
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    order: Mapped["Order"] = relationship("Order", back_populates="items")
    menu_item: Mapped["MenuItem"] = relationship("MenuItem")
    modifiers: Mapped[list["OrderItemModifier"]] = relationship(
        "OrderItemModifier", back_populates="order_item", cascade="all, delete-orphan"
    )
