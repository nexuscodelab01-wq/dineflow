"""Menu item ↔ modifier association ORM model."""

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.menu_item import MenuItem
    from app.models.menu_modifier import MenuModifier


class MenuItemModifier(Base):
    __tablename__ = "menu_item_modifiers"
    __table_args__ = (
        UniqueConstraint("menu_item_id", "modifier_id", name="uq_menu_item_modifier"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    menu_item_id: Mapped[int] = mapped_column(
        ForeignKey("menu_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    modifier_id: Mapped[int] = mapped_column(
        ForeignKey("menu_modifiers.id", ondelete="CASCADE"), nullable=False, index=True
    )

    menu_item: Mapped["MenuItem"] = relationship("MenuItem", back_populates="modifier_links")
    modifier: Mapped["MenuModifier"] = relationship("MenuModifier", back_populates="menu_item_links")
