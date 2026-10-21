"""Admin: register and manage the restaurant's smart card readers."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.exceptions import AppError, NotFoundError, raise_http_for_app_error
from app.db.session import get_db
from app.dependencies.features import requires_feature
from app.dependencies.restaurant import AdminUser, RestaurantId
from app.schemas.reader import ReaderRead, ReaderRegister
from app.services.reader_service import ReaderService

router = APIRouter(prefix="/admin/terminal", dependencies=[Depends(requires_feature("pos"))])


def _service(db: Annotated[Session, Depends(get_db)]) -> ReaderService:
    return ReaderService(db)


Service = Annotated[ReaderService, Depends(_service)]


@router.get("/readers", response_model=list[ReaderRead])
def list_readers(restaurant_id: RestaurantId, _: AdminUser, service: Service) -> list[ReaderRead]:
    return service.list_readers(restaurant_id)


@router.post("/readers", response_model=ReaderRead, status_code=201)
def register_reader(data: ReaderRegister, restaurant_id: RestaurantId, _: AdminUser, service: Service) -> ReaderRead:
    """Register a smart reader using the code shown on its screen (Settings → Generate pairing code on the reader)."""
    try:
        return service.register(restaurant_id, data.registration_code, data.label)
    except (AppError, NotFoundError) as exc:
        raise raise_http_for_app_error(exc) from exc


@router.delete("/readers/{reader_id}", status_code=204)
def remove_reader(reader_id: str, restaurant_id: RestaurantId, _: AdminUser, service: Service) -> None:
    try:
        service.remove(restaurant_id, reader_id)
    except (AppError, NotFoundError) as exc:
        raise raise_http_for_app_error(exc) from exc
