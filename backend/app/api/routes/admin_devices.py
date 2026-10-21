"""Admin-facing POS device management: pair, list, revoke, and set a staff member's PIN."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.exceptions import AppError, NotFoundError, raise_http_for_app_error
from app.db.session import get_db
from app.dependencies.restaurant import AdminUser, RestaurantId
from app.schemas.pos import (
    DevicePairRequest,
    DevicePairResponse,
    DeviceRead,
    PinLoginRequest,
)
from app.services.pos_service import PosService

router = APIRouter(prefix="/admin/devices")


def get_pos_service(db: Annotated[Session, Depends(get_db)]) -> PosService:
    return PosService(db)


Pos = Annotated[PosService, Depends(get_pos_service)]


@router.post("", response_model=DevicePairResponse, status_code=201)
def pair_device(data: DevicePairRequest, restaurant_id: RestaurantId, admin: AdminUser, service: Pos) -> DevicePairResponse:
    """Pair a new POS device (an iPad). The returned device_token is shown once — it's the pairing
    code the iPad is given, and there's no way to retrieve it again after this response."""
    return service.pair_device(restaurant_id, data.label, admin, data.kind)


@router.get("", response_model=list[DeviceRead])
def list_devices(restaurant_id: RestaurantId, _: AdminUser, service: Pos) -> list[DeviceRead]:
    return service.list_devices(restaurant_id)


@router.post("/{device_id}/revoke", status_code=204)
def revoke_device(device_id: int, restaurant_id: RestaurantId, admin: AdminUser, service: Pos) -> None:
    try:
        service.revoke_device(restaurant_id, device_id, admin)
    except (AppError, NotFoundError) as exc:
        raise raise_http_for_app_error(exc) from exc


@router.post("/staff/{membership_id}/pin", status_code=204)
def set_staff_pin(membership_id: int, data: PinLoginRequest, restaurant_id: RestaurantId, admin: AdminUser, service: Pos) -> None:
    """Set (or replace) a staff member's POS quick-switch PIN, by their RestaurantUser membership id."""
    try:
        service.set_pin(restaurant_id, membership_id, data.pin, admin)
    except (AppError, NotFoundError) as exc:
        raise raise_http_for_app_error(exc) from exc
