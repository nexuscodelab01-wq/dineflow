"""Category admin data access."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.category import Category


class CategoryRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_for_restaurant(self, restaurant_id: int, *, include_inactive: bool = True) -> list[Category]:
        stmt = select(Category).where(Category.restaurant_id == restaurant_id)
        if not include_inactive:
            stmt = stmt.where(Category.is_active.is_(True))
        stmt = stmt.order_by(Category.sort_order, Category.name)
        return list(self.db.scalars(stmt).all())

    def get_by_id(self, category_id: int) -> Category | None:
        return self.db.get(Category, category_id)

    def create(self, category: Category) -> Category:
        self.db.add(category)
        self.db.flush()
        return category

    def delete(self, category: Category) -> None:
        self.db.delete(category)
