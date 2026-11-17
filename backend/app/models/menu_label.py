"""Restaurant-defined labels for dishes: allergens ("Contains: …") and dish types (badges like "Vegan")."""

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin

LABEL_KINDS = ("allergen", "dish_type")


class MenuLabel(TimestampMixin, Base):
    """One allergen or dish type a restaurant offers.

    Dishes store the `code` (in `menu_items.allergens` / `menu_items.tags`), never the id, so a label can be renamed
    without touching a single dish. The code is generated once from the name and never changes.
    """

    __tablename__ = "menu_labels"
    __table_args__ = (UniqueConstraint("restaurant_id", "kind", "code", name="uq_menu_label_restaurant_kind_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(
        ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    code: Mapped[str] = mapped_column(String(60), nullable=False)
    label: Mapped[str] = mapped_column(String(60), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
