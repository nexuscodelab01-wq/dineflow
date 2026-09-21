"""Restaurant API routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, raise_http_for_app_error
from app.core.tenancy import resolve_tenant
from app.db.session import get_db
from app.dependencies.auth import require_roles
from app.models.enums import RoleName
from app.models.restaurant_table import RestaurantTable
from app.repositories.restaurant import RestaurantRepository
from app.schemas.restaurant import RestaurantRead
from app.services.reservation_service import ReservationService

router = APIRouter(prefix="/restaurants")


@router.get(
    "",
    response_model=list[RestaurantRead],
    dependencies=[Depends(require_roles(RoleName.SUPER_ADMIN))],
)
def list_restaurants(db: Annotated[Session, Depends(get_db)]) -> list[RestaurantRead]:
    """The platform directory. Restaurant sites never list each other, so this is platform-admin only."""
    restaurants = RestaurantRepository(db).list_active()
    return [RestaurantRead.model_validate(r) for r in restaurants]


@router.get("/{identifier}", response_model=RestaurantRead)
def get_restaurant(identifier: str, db: Annotated[Session, Depends(get_db)]) -> RestaurantRead:
    restaurant = RestaurantRepository(db).get_by_id_or_slug(identifier)
    if restaurant is None or not restaurant.is_active:
        raise raise_http_for_app_error(NotFoundError("Restaurant not found"))
    return RestaurantRead.model_validate(restaurant)


@router.get("/{identifier}/tables")
def list_tables(
    identifier: str,
    db: Annotated[Session, Depends(get_db)],
    available_only: bool = Query(default=True),
) -> list[dict]:
    restaurant = RestaurantRepository(db).get_by_id_or_slug(identifier)
    if restaurant is None:
        raise raise_http_for_app_error(NotFoundError("Restaurant not found"))

    ReservationService(db).refresh_floor_status(restaurant.id)
    stmt = select(RestaurantTable).where(
        RestaurantTable.restaurant_id == restaurant.id, RestaurantTable.is_active.is_(True)
    )
    if available_only:
        from app.models.enums import TableStatus

        stmt = stmt.where(RestaurantTable.status == TableStatus.AVAILABLE)
    stmt = stmt.order_by(RestaurantTable.table_number)
    tables = db.scalars(stmt).all()
    return [
        {
            "id": table.id,
            "table_number": table.table_number,
            "capacity": table.capacity,
            "zone": table.zone,
            "shape": table.shape,
            "pos_x": table.pos_x,
            "pos_y": table.pos_y,
            "status": table.status.value if hasattr(table.status, "value") else str(table.status),
        }
        for table in tables
    ]
