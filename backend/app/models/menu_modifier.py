"""Menu modifier ORM model."""

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.menu_item_modifier import MenuItemModifier
    from app.models.menu_modifier_option import MenuModifierOption
    from app.models.restaurant import Restaurant


class MenuModifier(TimestampMixin, Base):
    __tablename__ = "menu_modifiers"

    id: Mapped[int] = mapped_column(primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(
        ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    min_selections: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_selections: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    restaurant: Mapped["Restaurant"] = relationship("Restaurant", back_populates="modifiers")
    options: Mapped[list["MenuModifierOption"]] = relationship(
        "MenuModifierOption", back_populates="modifier", cascade="all, delete-orphan"
    )
    menu_item_links: Mapped[list["MenuItemModifier"]] = relationship(
        "MenuItemModifier", back_populates="modifier", cascade="all, delete-orphan"
    )
