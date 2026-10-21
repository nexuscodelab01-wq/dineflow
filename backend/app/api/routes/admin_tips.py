"""Admin tips: the period report (what each person collected and is owed under the pooling policy), the
finalize action that writes it into the ledger, and syncing on-reader tipping to the restaurant's Stripe account."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.exceptions import AppError, NotFoundError, raise_http_for_app_error
from app.db.session import get_db
from app.dependencies.features import requires_feature
from app.dependencies.restaurant import AdminUser, RestaurantId
from app.schemas.tips import (
    TerminalSyncRead,
    TipAllocationRead,
    TipRange,
    TipReportRead,
)
from app.services.terminal_service import TerminalService
from app.services.tip_service import TipService

router = APIRouter(prefix="/admin", dependencies=[Depends(requires_feature("tips"))])


def get_tip_service(db: Annotated[Session, Depends(get_db)]) -> TipService:
    return TipService(db)


def get_terminal_service(db: Annotated[Session, Depends(get_db)]) -> TerminalService:
    return TerminalService(db)


Tips = Annotated[TipService, Depends(get_tip_service)]
Terminal = Annotated[TerminalService, Depends(get_terminal_service)]


@router.get("/tips/report", response_model=TipReportRead)
def tip_report(restaurant_id: RestaurantId, _: AdminUser, service: Tips, start: Annotated[datetime, Query()], end: Annotated[datetime, Query()]) -> TipReportRead:
    try:
        TipRange(start=start, end=end)
        return service.report(restaurant_id, start, end)
    except (AppError, NotFoundError, ValueError) as exc:
        raise raise_http_for_app_error(exc if isinstance(exc, AppError) else AppError(str(exc))) from exc


@router.post("/tips/finalize", response_model=TipReportRead)
def finalize_tips(data: TipRange, restaurant_id: RestaurantId, admin: AdminUser, service: Tips) -> TipReportRead:
    try:
        return service.finalize(restaurant_id, data.start, data.end, admin)
    except (AppError, NotFoundError) as exc:
        raise raise_http_for_app_error(exc) from exc


@router.get("/tips/history", response_model=list[TipAllocationRead])
def tip_history(restaurant_id: RestaurantId, _: AdminUser, service: Tips) -> list[TipAllocationRead]:
    return service.history(restaurant_id)


@router.post("/settings/terminal/sync", response_model=TerminalSyncRead)
def sync_terminal(restaurant_id: RestaurantId, _: AdminUser, service: Terminal) -> TerminalSyncRead:
    """Push the tip settings to Stripe so the card reader shows the tip screen (or stops showing it)."""
    try:
        result = service.sync_tipping(restaurant_id)
    except (AppError, NotFoundError) as exc:
        raise raise_http_for_app_error(exc) from exc
    return TerminalSyncRead(location_id=str(result["location_id"]), configuration_id=str(result["configuration_id"]), tipping=bool(result["tipping"]))
