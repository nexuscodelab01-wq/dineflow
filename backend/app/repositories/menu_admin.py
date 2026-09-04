"""Menu item and modifier admin data access."""

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.menu_item import MenuItem
from app.models.menu_item_modifier import MenuItemModifier
from app.models.menu_modifier import MenuModifier
from app.models.menu_modifier_option import MenuModifierOption


class MenuAdminRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_items(self, restaurant_id: int) -> list[MenuItem]:
        stmt = (
            select(MenuItem)
            .where(MenuItem.restaurant_id == restaurant_id)
            .order_by(MenuItem.sort_order, MenuItem.name)
        )
        return list(self.db.scalars(stmt).all())

    def get_item(self, item_id: int) -> MenuItem | None:
        stmt = (
            select(MenuItem)
            .options(
                selectinload(MenuItem.modifier_links).selectinload(MenuItemModifier.modifier).selectinload(MenuModifier.options)
            )
            .where(MenuItem.id == item_id)
        )
        return self.db.scalar(stmt)

    def create_item(self, item: MenuItem) -> MenuItem:
        self.db.add(item)
        self.db.flush()
        return item

    def delete_item(self, item: MenuItem) -> None:
        self.db.delete(item)

    def set_item_modifiers(self, item: MenuItem, modifier_ids: list[int]) -> None:
        item.modifier_links.clear()
        self.db.flush()
        for modifier_id in modifier_ids:
            self.db.add(MenuItemModifier(menu_item_id=item.id, modifier_id=modifier_id))

    def list_modifiers(self, restaurant_id: int) -> list[MenuModifier]:
        stmt = (
            select(MenuModifier)
            .options(selectinload(MenuModifier.options))
            .where(MenuModifier.restaurant_id == restaurant_id)
            .order_by(MenuModifier.sort_order, MenuModifier.name)
        )
        return list(self.db.scalars(stmt).unique().all())

    def get_modifier(self, modifier_id: int) -> MenuModifier | None:
        stmt = (
            select(MenuModifier)
            .options(selectinload(MenuModifier.options))
            .where(MenuModifier.id == modifier_id)
        )
        return self.db.scalar(stmt)

    def create_modifier(self, modifier: MenuModifier) -> MenuModifier:
        self.db.add(modifier)
        self.db.flush()
        return modifier

    def delete_modifier(self, modifier: MenuModifier) -> None:
        self.db.delete(modifier)

    def get_option(self, option_id: int) -> MenuModifierOption | None:
        return self.db.get(MenuModifierOption, option_id)

    def create_option(self, option: MenuModifierOption) -> MenuModifierOption:
        self.db.add(option)
        self.db.flush()
        return option

    def delete_option(self, option: MenuModifierOption) -> None:
        self.db.delete(option)
