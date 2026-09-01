"""Menu API routes."""

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, raise_http_for_app_error
from app.db.session import get_db
from app.schemas.menu import CategoryRead, MenuItemDetailRead, MenuListResponse
from app.services.menu_service import MenuService

router = APIRouter()


def get_menu_service(db: Annotated[Session, Depends(get_db)]) -> MenuService:
    return MenuService(db)


@router.get("/categories", response_model=list[CategoryRead])
def list_categories(
    restaurant_id: int,
    service: Annotated[MenuService, Depends(get_menu_service)],
) -> list[CategoryRead]:
    return service.list_categories(restaurant_id)


@router.get("/menu", response_model=MenuListResponse)
def list_menu(
    restaurant_id: int,
    service: Annotated[MenuService, Depends(get_menu_service)],
    search: str | None = None,
    category_id: int | None = None,
    is_vegetarian: bool | None = None,
    is_spicy: bool | None = None,
    is_available: bool | None = Query(default=True),
    is_popular: bool | None = None,
    price_min: Decimal | None = None,
    price_max: Decimal | None = None,
    sort: str = Query(default="popular", pattern="^(popular|name|price_asc|price_desc)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> MenuListResponse:
    return service.list_items(
        restaurant_id=restaurant_id,
        search=search,
        category_id=category_id,
        is_vegetarian=is_vegetarian,
        is_spicy=is_spicy,
        is_available=is_available,
        is_popular=is_popular,
        price_min=price_min,
        price_max=price_max,
        sort=sort,
        page=page,
        page_size=page_size,
    )


@router.get("/menu/{item_id}", response_model=MenuItemDetailRead)
def get_menu_item(
    item_id: int,
    service: Annotated[MenuService, Depends(get_menu_service)],
) -> MenuItemDetailRead:
    try:
        return service.get_item(item_id)
    except NotFoundError as exc:
        raise raise_http_for_app_error(exc) from exc
