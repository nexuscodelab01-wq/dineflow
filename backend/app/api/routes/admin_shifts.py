"""Admin-facing historical shift / Z-report review — mirrors admin_devices.py's AdminUser gating."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.restaurant import AdminUser, RestaurantId
from app.schemas.shift import ShiftReportRead
from app.services.shift_service import ShiftService

router = APIRouter(prefix="/admin/shifts")


def get_shift_service(db: Annotated[Session, Depends(get_db)]) -> ShiftService:
    return ShiftService(db)


Shifts = Annotated[ShiftService, Depends(get_shift_service)]


@router.get("", response_model=list[ShiftReportRead])
def list_shifts(restaurant_id: RestaurantId, _: AdminUser, service: Shifts) -> list[ShiftReportRead]:
    return service.list_shifts(restaurant_id)
