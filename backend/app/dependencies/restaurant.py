"""Restaurant-scoped authorization helpers."""

from typing import Annotated

from fastapi import Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ForbiddenError, NotFoundError
from app.db.session import get_db
from app.dependencies.auth import CurrentUser, require_roles
from app.models.enums import RoleName
from app.models.restaurant_user import RestaurantUser
from app.models.user import User
from app.repositories.restaurant import RestaurantRepository


def get_role_name(user: User) -> str:
    return user.role.name.value if hasattr(user.role.name, "value") else str(user.role.name)


def user_can_access_restaurant(db: Session, user: User, restaurant_id: int) -> bool:
    role = get_role_name(user)
    if role == RoleName.SUPER_ADMIN.value:
        return True
    if role in {RoleName.RESTAURANT_ADMIN.value, RoleName.RESTAURANT_STAFF.value}:
        membership = db.scalar(
            select(RestaurantUser).where(
                RestaurantUser.restaurant_id == restaurant_id,
                RestaurantUser.user_id == user.id,
            )
        )
        return membership is not None
    return False


StaffUser = Annotated[User, Depends(require_roles(RoleName.RESTAURANT_STAFF, RoleName.RESTAURANT_ADMIN, RoleName.SUPER_ADMIN))]
AdminUser = Annotated[User, Depends(require_roles(RoleName.RESTAURANT_ADMIN, RoleName.SUPER_ADMIN))]


def get_restaurant_id(
    restaurant_id: Annotated[int, Query(description="Restaurant ID")],
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> int:
    restaurant = RestaurantRepository(db).get_by_id(restaurant_id)
    if restaurant is None:
        raise NotFoundError("Restaurant not found")
    if not user_can_access_restaurant(db, current_user, restaurant_id):
        raise ForbiddenError("No access to this restaurant")
    return restaurant_id


RestaurantId = Annotated[int, Depends(get_restaurant_id)]
