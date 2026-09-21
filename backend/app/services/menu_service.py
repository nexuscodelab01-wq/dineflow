"""Menu business logic."""

import math

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.repositories.menu import MenuRepository
from app.schemas.menu import (
    CategoryRead,
    MenuItemDetailRead,
    MenuItemListRead,
    MenuListResponse,
    MenuModifierRead,
    ModifierOptionRead,
)


class MenuService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.menu = MenuRepository(db)

    def list_categories(self, restaurant_id: int) -> list[CategoryRead]:
        categories = self.menu.list_categories(restaurant_id)
        return [CategoryRead.model_validate(c) for c in categories]

    def list_items(self, **filters) -> MenuListResponse:
        items, total = self.menu.list_items(**filters)
        page = filters.get("page", 1)
        page_size = filters.get("page_size", 20)
        pages = max(1, math.ceil(total / page_size)) if total else 1
        return MenuListResponse(
            items=[self._to_list_item(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )

    def get_item(self, item_id: int, restaurant_id: int) -> MenuItemDetailRead:
        item = self.menu.get_item_detail(item_id)
        if item is None or item.restaurant_id != restaurant_id:
            raise NotFoundError("Menu item not found")
        return self._to_detail_item(item)

    def _to_list_item(self, item) -> MenuItemListRead:
        return MenuItemListRead(
            id=item.id,
            restaurant_id=item.restaurant_id,
            category_id=item.category_id,
            category_name=item.category.name if item.category else None,
            name=item.name,
            description=item.description,
            price=item.price,
            image_url=item.image_url,
            is_available=item.is_available,
            preparation_time_minutes=item.preparation_time_minutes,
            is_vegetarian=item.is_vegetarian,
            is_spicy=item.is_spicy,
            is_popular=item.is_popular,
        )

    def _to_detail_item(self, item) -> MenuItemDetailRead:
        modifiers: list[MenuModifierRead] = []
        for link in sorted(item.modifier_links, key=lambda l: l.modifier.sort_order):
            modifier = link.modifier
            modifiers.append(
                MenuModifierRead(
                    id=modifier.id,
                    name=modifier.name,
                    description=modifier.description,
                    is_required=modifier.is_required,
                    min_selections=modifier.min_selections,
                    max_selections=modifier.max_selections,
                    sort_order=modifier.sort_order,
                    options=[
                        ModifierOptionRead.model_validate(opt)
                        for opt in sorted(modifier.options, key=lambda o: o.sort_order)
                    ],
                )
            )
        base = self._to_list_item(item)
        return MenuItemDetailRead(**base.model_dump(), modifiers=modifiers)
