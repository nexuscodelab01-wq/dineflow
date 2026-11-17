"""A restaurant's own allergens and dish types.

Dishes keep the label's *code* in `menu_items.allergens` / `menu_items.tags`. Renaming a label only changes what is
shown; deleting one also takes its code off every dish, so no dish is left carrying something that no longer exists.
"""

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.allergens import ALLERGENS
from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.models.menu_item import MenuItem
from app.models.menu_label import LABEL_KINDS, MenuLabel
from app.models.restaurant import Restaurant
from app.schemas.labels import LabelCreate, LabelRead, LabelUpdate

ITEM_FIELD = {"allergen": MenuItem.allergens, "dish_type": MenuItem.tags}
ITEM_ATTR = {"allergen": "allergens", "dish_type": "tags"}
KIND_NOUN = {"allergen": "allergen", "dish_type": "dish type"}
MAX_PER_KIND = 100


def make_code(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")[:50] or "label"


class LabelService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def ensure_defaults(self, restaurant_id: int) -> None:
        """Give a restaurant the standard 14 allergens the first time it is needed, exactly once."""
        restaurant = self.db.get(Restaurant, restaurant_id)
        if restaurant is None or restaurant.labels_seeded:
            return
        for position, (code, label) in enumerate(ALLERGENS.items()):
            self.db.add(MenuLabel(restaurant_id=restaurant_id, kind="allergen", code=code, label=label, sort_order=position))
        restaurant.labels_seeded = True
        self.db.flush()

    def list_labels(self, restaurant_id: int, kind: str | None = None, *, with_counts: bool = False) -> list[LabelRead]:
        self.ensure_defaults(restaurant_id)
        stmt = select(MenuLabel).where(MenuLabel.restaurant_id == restaurant_id)
        if kind is not None:
            stmt = stmt.where(MenuLabel.kind == kind)
        labels = self.db.scalars(stmt.order_by(MenuLabel.kind, MenuLabel.sort_order, MenuLabel.label)).all()
        out = [LabelRead.model_validate(label) for label in labels]
        if with_counts:
            items = self.db.execute(
                select(MenuItem.allergens, MenuItem.tags).where(MenuItem.restaurant_id == restaurant_id)
            ).all()
            for read in out:
                position = 0 if read.kind == "allergen" else 1
                read.item_count = sum(1 for row in items if read.code in (row[position] or []))
        return out

    def create(self, restaurant_id: int, data: LabelCreate) -> LabelRead:
        self.ensure_defaults(restaurant_id)
        rows = self._rows(restaurant_id, data.kind)
        if len(rows) >= MAX_PER_KIND:
            raise AppError(f"You can have up to {MAX_PER_KIND} {KIND_NOUN[data.kind]}s")
        if any(r.label.lower() == data.label.lower() for r in rows):
            raise ConflictError(f"“{data.label}” already exists")
        taken = {r.code for r in rows}
        base, code, n = make_code(data.label), make_code(data.label), 2
        while code in taken:
            code, n = f"{base}_{n}", n + 1
        row = MenuLabel(
            restaurant_id=restaurant_id, kind=data.kind, code=code, label=data.label,
            sort_order=max((r.sort_order for r in rows), default=-1) + 1,
        )
        self.db.add(row)
        self.db.commit()
        return LabelRead.model_validate(row)

    def update(self, label_id: int, data: LabelUpdate, restaurant_id: int) -> LabelRead:
        row = self._get(label_id, restaurant_id)
        for other in self._rows(restaurant_id, row.kind):
            if other.id != row.id and other.label.lower() == data.label.lower():
                raise ConflictError(f"“{data.label}” already exists")
        row.label = data.label
        self.db.commit()
        return LabelRead.model_validate(row)

    def delete(self, label_id: int, restaurant_id: int) -> int:
        """Delete a label and take its code off every dish. Returns how many dishes were changed."""
        row = self._get(label_id, restaurant_id)
        attr = ITEM_ATTR[row.kind]
        changed = 0
        for item in self.db.scalars(select(MenuItem).where(MenuItem.restaurant_id == restaurant_id)).all():
            current = list(getattr(item, attr) or [])
            if row.code in current:
                setattr(item, attr, [c for c in current if c != row.code])  # new list so the JSONB change is seen
                changed += 1
        self.db.delete(row)
        self.db.commit()
        return changed

    def check_codes(self, restaurant_id: int, kind: str, codes: list[str] | None) -> list[str] | None:
        """Every code a dish is given must be one of this restaurant's labels (duplicates collapsed, order kept)."""
        if codes is None:
            return None
        self.ensure_defaults(restaurant_id)
        valid = {r.code for r in self._rows(restaurant_id, kind)}
        unknown = sorted(set(codes) - valid)
        if unknown:
            raise AppError(f"Unknown {KIND_NOUN[kind]}(s): {', '.join(unknown)}")
        return list(dict.fromkeys(codes))

    def _rows(self, restaurant_id: int, kind: str) -> list[MenuLabel]:
        return list(
            self.db.scalars(select(MenuLabel).where(MenuLabel.restaurant_id == restaurant_id, MenuLabel.kind == kind)).all()
        )

    def _get(self, label_id: int, restaurant_id: int) -> MenuLabel:
        row = self.db.get(MenuLabel, label_id)
        if row is None or row.restaurant_id != restaurant_id:
            raise NotFoundError("Label not found")
        return row
