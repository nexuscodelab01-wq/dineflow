"""Routes reachable from a paired POS device: PIN login, counter orders, dine-in orders, cash tender.

Device-token/pos_session-token gated (app.dependencies.pos), not JWT — a POS device has no CurrentUser.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.exceptions import AppError, NotFoundError, raise_http_for_app_error
from app.db.session import get_db
from app.dependencies.features import (
    requires_feature_for_device,
    requires_feature_for_pos_staff,
)
from app.dependencies.pos import CurrentDevice, CurrentPosStaff
from app.models.table_session import TableSession
from app.schemas.pos import (
    OpenTableSessionsResponse,
    PinLoginRequest,
    PinLoginResponse,
    PosOrderCreate,
    PosOrderRead,
)
from app.schemas.table_session import RoundCreate, SessionRoundRead
from app.services.pos_service import PosService
from app.services.table_session_service import TableSessionService

router = APIRouter(prefix="/pos")

POS_GATE = [Depends(requires_feature_for_device("pos"))]  # device-token-only routes
POS_STAFF_GATE = [Depends(requires_feature_for_pos_staff("pos"))]  # pos_session-token routes


def get_pos_service(db: Annotated[Session, Depends(get_db)]) -> PosService:
    return PosService(db)


Pos = Annotated[PosService, Depends(get_pos_service)]


@router.post("/auth/pin-login", response_model=PinLoginResponse)
def pin_login(data: PinLoginRequest, device: CurrentDevice, service: Pos) -> PinLoginResponse:
    try:
        return service.pin_login(device.device, data.pin)
    except AppError as exc:
        raise raise_http_for_app_error(exc) from exc


@router.get("/table-sessions/open", response_model=OpenTableSessionsResponse, dependencies=POS_GATE)
def open_table_sessions(device: CurrentDevice, db: Annotated[Session, Depends(get_db)]) -> OpenTableSessionsResponse:
    sessions = TableSessionService(db).open_sessions(device.device.restaurant_id)
    return OpenTableSessionsResponse(sessions=sessions)


@router.post("/table-sessions/{session_id}/orders", response_model=SessionRoundRead, dependencies=POS_STAFF_GATE)
def pos_table_order(
    session_id: int, data: RoundCreate, staff: CurrentPosStaff, db: Annotated[Session, Depends(get_db)],
) -> SessionRoundRead:
    """A dine-in round sent from the POS on a table's behalf — delegates straight to the existing
    waiter-view path (TableSessionService.place_round), unchanged."""
    session = db.get(TableSession, session_id)
    if session is None or session.restaurant_id != staff.device.restaurant_id:
        raise raise_http_for_app_error(NotFoundError("Session not found"))
    try:
        return TableSessionService(db).place_round(guest=None, session=session, data=data, client_token=None, staff_user=staff.user)
    except AppError as exc:
        raise raise_http_for_app_error(exc) from exc


@router.post("/orders", response_model=PosOrderRead, status_code=201, dependencies=POS_STAFF_GATE)
def create_counter_order(data: PosOrderCreate, staff: CurrentPosStaff, service: Pos) -> PosOrderRead:
    try:
        return service.create_counter_order(staff.device.restaurant_id, staff.user, data)
    except AppError as exc:
        raise raise_http_for_app_error(exc) from exc


@router.post("/orders/{order_id}/pay-cash", status_code=204, dependencies=POS_STAFF_GATE)
def pay_cash(order_id: int, staff: CurrentPosStaff, service: Pos) -> None:
    try:
        service.mark_counter_order_paid_cash(staff.device.restaurant_id, order_id, staff.user)
    except (AppError, NotFoundError) as exc:
        raise raise_http_for_app_error(exc) from exc
