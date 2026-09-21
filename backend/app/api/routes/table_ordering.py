"""QR table ordering for guests: no account, just the table's QR code."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.routes.realtime import sse_response
from app.core.exceptions import AppError, raise_http_for_app_error
from app.core.realtime import session_topic
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.dependencies.guest import CurrentGuest
from app.schemas.table_session import JoinRequest, JoinResponse, RoundCreate, SessionRead, SessionRoundRead, TableInfo
from app.services.table_session_service import TableSessionService

router = APIRouter()


def get_service(db: Annotated[Session, Depends(get_db)]) -> TableSessionService:
    return TableSessionService(db)


Service = Annotated[TableSessionService, Depends(get_service)]


@router.get("/t/{token}", response_model=TableInfo, dependencies=[rate_limit("qr-info", 60, 60)])
def table_info(token: str, service: Service, restaurant_id: int | None = None) -> TableInfo:
    try:
        return service.info(token, restaurant_id)
    except AppError as exc:
        raise raise_http_for_app_error(exc) from exc


@router.post("/t/{token}/join", response_model=JoinResponse, dependencies=[rate_limit("qr-join", 20, 600)])
def join_table(token: str, data: JoinRequest, service: Service, restaurant_id: int | None = None) -> JoinResponse:
    try:
        return service.join(token, data.name, restaurant_id)
    except AppError as exc:
        raise raise_http_for_app_error(exc) from exc


@router.get("/table-session", response_model=SessionRead)
def my_table_session(guest: CurrentGuest, service: Service) -> SessionRead:
    return service.view(guest.session)


@router.post(
    "/table-session/orders",
    response_model=SessionRoundRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[rate_limit("qr-order", 30, 600)],
)
def send_round(
    data: RoundCreate,
    guest: CurrentGuest,
    service: Service,
    idempotency_key: Annotated[str | None, Header(max_length=64)] = None,
) -> SessionRoundRead:
    """Send items to the kitchen as a new round. Sending the same `Idempotency-Key` again returns the same round."""
    try:
        return service.place_round(guest.guest, guest.session, data, idempotency_key)
    except AppError as exc:
        raise raise_http_for_app_error(exc) from exc


@router.get("/table-session/stream", summary="Live updates for your table's tab (text/event-stream)")
async def table_stream(request: Request, guest: CurrentGuest) -> StreamingResponse:
    """Sends `round.created`, `order.status` and `session.closed` events for the table the pass belongs to."""
    return sse_response(request, session_topic(guest.session.id))
