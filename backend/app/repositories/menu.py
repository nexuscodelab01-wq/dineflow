"""Menu data access with filtering and pagination."""

from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.category import Category
from app.models.menu_item import MenuItem
from app.models.menu_item_modifier import MenuItemModifier
from app.models.menu_modifier import MenuModifier


class MenuRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_categories(self, restaurant_id: int, *, active_only: bool = True) -> list[Category]:
        stmt = select(Category).where(Category.restaurant_id == restaurant_id)
        if active_only:
            stmt = stmt.where(Category.is_active.is_(True))
        stmt = stmt.order_by(Category.sort_order, Category.name)
        return list(self.db.scalars(stmt).all())

    def list_items(
        self,
        *,
        restaurant_id: int,
        search: str | None = None,
        category_id: int | None = None,
        is_vegetarian: bool | None = None,
        is_spicy: bool | None = None,
        is_available: bool | None = None,
        is_popular: bool | None = None,
        price_min: Decimal | None = None,
        price_max: Decimal | None = None,
        sort: str = "popular",
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[MenuItem], int]:
        stmt = select(MenuItem).where(MenuItem.restaurant_id == restaurant_id)

        if search:
            pattern = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(MenuItem.name.ilike(pattern), MenuItem.description.ilike(pattern))
            )
        if category_id is not None:
            stmt = stmt.where(MenuItem.category_id == category_id)
        if is_vegetarian is not None:
            stmt = stmt.where(MenuItem.is_vegetarian.is_(is_vegetarian))
        if is_spicy is not None:
            stmt = stmt.where(MenuItem.is_spicy.is_(is_spicy))
        if is_available is not None:
            stmt = stmt.where(MenuItem.is_available.is_(is_available))
        if is_popular is not None:
            stmt = stmt.where(MenuItem.is_popular.is_(is_popular))
        if price_min is not None:
            stmt = stmt.where(MenuItem.price >= price_min)
        if price_max is not None:
            stmt = stmt.where(MenuItem.price <= price_max)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = self.db.scalar(count_stmt) or 0

        stmt = (
            stmt.options(joinedload(MenuItem.category))
        )

        sort_map = {
            "popular": (MenuItem.is_popular.desc(), MenuItem.sort_order, MenuItem.name),
            "name": (MenuItem.name.asc(),),
            "price_asc": (MenuItem.price.asc(), MenuItem.name.asc()),
            "price_desc": (MenuItem.price.desc(), MenuItem.name.asc()),
        }
        for column in sort_map.get(sort, sort_map["popular"]):
            stmt = stmt.order_by(column)

        offset = (page - 1) * page_size
        items = list(self.db.scalars(stmt.offset(offset).limit(page_size)).unique().all())
        return items, total

    def get_item_detail(self, item_id: int) -> MenuItem | None:
        stmt = (
            select(MenuItem)
            .options(
                joinedload(MenuItem.category),
                selectinload(MenuItem.modifier_links)
                .joinedload(MenuItemModifier.modifier)
                .selectinload(MenuModifier.options),
            )
            .where(MenuItem.id == item_id)
        )
        return self.db.scalar(stmt)

    def get_items_by_ids(self, item_ids: list[int], restaurant_id: int) -> list[MenuItem]:
        if not item_ids:
            return []
        stmt = (
            select(MenuItem)
            .options(
                selectinload(MenuItem.modifier_links)
                .joinedload(MenuItemModifier.modifier)
                .selectinload(MenuModifier.options),
            )
            .where(MenuItem.id.in_(item_ids), MenuItem.restaurant_id == restaurant_id)
        )
        return list(self.db.scalars(stmt).unique().all())
