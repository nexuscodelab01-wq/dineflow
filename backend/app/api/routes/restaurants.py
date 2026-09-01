"""Restaurant API routes."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, raise_http_for_app_error
from app.db.session import get_db
from app.repositories.restaurant import RestaurantRepository
from app.schemas.restaurant import RestaurantRead

router = APIRouter(prefix="/restaurants")


@router.get("", response_model=list[RestaurantRead])
def list_restaurants(db: Annotated[Session, Depends(get_db)]) -> list[RestaurantRead]:
    restaurants = RestaurantRepository(db).list_active()
    return [RestaurantRead.model_validate(r) for r in restaurants]


@router.get("/{identifier}", response_model=RestaurantRead)
def get_restaurant(identifier: str, db: Annotated[Session, Depends(get_db)]) -> RestaurantRead:
    restaurant = RestaurantRepository(db).get_by_id_or_slug(identifier)
    if restaurant is None or not restaurant.is_active:
        raise raise_http_for_app_error(NotFoundError("Restaurant not found"))
    return RestaurantRead.model_validate(restaurant)
