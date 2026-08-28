"""Menu modifier option ORM model."""

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.menu_modifier import MenuModifier


class MenuModifierOption(Base):
    __tablename__ = "menu_modifier_options"

    id: Mapped[int] = mapped_column(primary_key=True)
    modifier_id: Mapped[int] = mapped_column(
        ForeignKey("menu_modifiers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    price_adjustment: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    modifier: Mapped["MenuModifier"] = relationship("MenuModifier", back_populates="options")
