"""Order item modifier snapshot ORM model."""

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.menu_modifier_option import MenuModifierOption
    from app.models.order_item import OrderItem


class OrderItemModifier(Base):
    __tablename__ = "order_item_modifiers"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_item_id: Mapped[int] = mapped_column(
        ForeignKey("order_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    modifier_option_id: Mapped[int | None] = mapped_column(
        ForeignKey("menu_modifier_options.id", ondelete="SET NULL"), nullable=True
    )
    modifier_name: Mapped[str] = mapped_column(String(100), nullable=False)
    option_name: Mapped[str] = mapped_column(String(100), nullable=False)
    price_adjustment: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"), nullable=False)

    order_item: Mapped["OrderItem"] = relationship("OrderItem", back_populates="modifiers")
    modifier_option: Mapped["MenuModifierOption | None"] = relationship("MenuModifierOption")
