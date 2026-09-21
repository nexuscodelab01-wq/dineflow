"""Public and customer reservation routes."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.tenancy import ensure_customer_of
from app.services.feature_service import FeatureService
from app.core.exceptions import AppError, NotFoundError, raise_http_for_app_error
from app.db.session import get_db
from app.core.rate_limit import rate_limit
from app.dependencies.auth import CurrentUser
from app.repositories.restaurant import RestaurantRepository
from app.schemas.reservation import (
    AvailabilityResponse,
    ReservationCreate,
    ReservationRead,
)
from app.services.reservation_service import DEFAULT_DURATION_MINUTES, ReservationService

router = APIRouter()


def get_reservation_service(db: Annotated[Session, Depends(get_db)]) -> ReservationService:
    return ReservationService(db)


def _restaurant_id(identifier: str, db: Session) -> int:
    restaurant = RestaurantRepository(db).get_by_id_or_slug(identifier)
    if restaurant is None or not restaurant.is_active:
        raise raise_http_for_app_error(NotFoundError("Restaurant not found"))
    return restaurant.id


@router.get(
    "/restaurants/{identifier}/reservations/availability",
    response_model=AvailabilityResponse,
    dependencies=[rate_limit("availability", 90, 60)],
)
def reservation_availability(
    identifier: str,
    db: Annotated[Session, Depends(get_db)],
    service: Annotated[ReservationService, Depends(get_reservation_service)],
    starts_at: datetime = Query(...),
    party_size: int = Query(..., ge=1, le=20),
    duration_minutes: int = Query(default=DEFAULT_DURATION_MINUTES, ge=30, le=240),
) -> AvailabilityResponse:
    try:
        restaurant_id = _restaurant_id(identifier, db)
        FeatureService(db).require(restaurant_id, "reservations")
        return service.get_availability(
            restaurant_id,
            starts_at=starts_at,
            party_size=party_size,
            duration_minutes=duration_minutes,
        )
    except (AppError, NotFoundError) as exc:
        raise raise_http_for_app_error(exc) from exc


@router.post(
    "/restaurants/{identifier}/reservations",
    response_model=ReservationRead,
    status_code=201,
    dependencies=[rate_limit("reserve", 20, 600)],
)
def create_reservation(
    identifier: str,
    payload: ReservationCreate,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    service: Annotated[ReservationService, Depends(get_reservation_service)],
) -> ReservationRead:
    try:
        restaurant_id = _restaurant_id(identifier, db)
        FeatureService(db).require(restaurant_id, "reservations")
        ensure_customer_of(user, restaurant_id)
        return service.create_reservation(restaurant_id, payload, user)
    except (AppError, NotFoundError) as exc:
        raise raise_http_for_app_error(exc) from exc


@router.get("/reservations/me", response_model=list[ReservationRead])
def my_reservations(
    user: CurrentUser,
    service: Annotated[ReservationService, Depends(get_reservation_service)],
    restaurant_id: int | None = None,
    include_past: bool = Query(default=False, description="Also return finished/cancelled/expired bookings"),
) -> list[ReservationRead]:
    return service.list_user_reservations(user.id, restaurant_id, include_past=include_past)


@router.post("/reservations/{reservation_id}/confirm", response_model=ReservationRead)
def confirm_reservation(
    reservation_id: int,
    user: CurrentUser,
    service: Annotated[ReservationService, Depends(get_reservation_service)],
) -> ReservationRead:
    try:
        return service.confirm_hold(reservation_id, user.id)
    except (AppError, NotFoundError) as exc:
        raise raise_http_for_app_error(exc) from exc


@router.post("/reservations/{reservation_id}/cancel", response_model=ReservationRead)
def cancel_reservation(
    reservation_id: int,
    user: CurrentUser,
    service: Annotated[ReservationService, Depends(get_reservation_service)],
) -> ReservationRead:
    try:
        return service.cancel_reservation(reservation_id, user.id)
    except (AppError, NotFoundError) as exc:
        raise raise_http_for_app_error(exc) from exc
