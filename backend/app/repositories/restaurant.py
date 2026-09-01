"""Restaurant data access."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.restaurant import Restaurant


class RestaurantRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_active(self) -> list[Restaurant]:
        stmt = select(Restaurant).where(Restaurant.is_active.is_(True)).order_by(Restaurant.name)
        return list(self.db.scalars(stmt).all())

    def get_by_id(self, restaurant_id: int) -> Restaurant | None:
        return self.db.get(Restaurant, restaurant_id)

    def get_by_slug(self, slug: str) -> Restaurant | None:
        return self.db.scalar(select(Restaurant).where(Restaurant.slug == slug))

    def get_by_id_or_slug(self, identifier: str) -> Restaurant | None:
        if identifier.isdigit():
            restaurant = self.get_by_id(int(identifier))
            if restaurant:
                return restaurant
        return self.get_by_slug(identifier)
