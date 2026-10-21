"""Routes reachable from a paired POS device: PIN login, counter orders, dine-in orders, cash tender.

Device-token/pos_session-token gated (app.dependencies.pos), not JWT — a POS device has no CurrentUser.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AppError, NotFoundError, raise_http_for_app_error
from app.db.session import get_db
from app.dependencies.features import (
    requires_feature_for_device,
    requires_feature_for_pos_staff,
)
from app.dependencies.pos import CurrentDevice, CurrentPosStaff
from app.models.restaurant import Restaurant
from app.models.table_session import TableSession
from app.schemas.menu import MenuListResponse
from app.schemas.pos import (
    AvailabilityRead,
    AvailabilityRequest,
    AwaitingPaymentRead,
    OpenTableSessionsResponse,
    PinLoginRequest,
    PinLoginResponse,
    PosCardIntentRead,
    PosConnectionTokenRead,
    PosCouponPreviewRead,
    PosCouponPreviewRequest,
    PosCustomerRead,
    PosOrderCreate,
    PosOrderRead,
)
from app.schemas.shift import (
    CashMovementCreate,
    ShiftCloseRequest,
    ShiftOpenRequest,
    ShiftRead,
    ShiftReportRead,
)
from app.schemas.table_session import (
    BarTabRequest,
    FireCourseRead,
    FireCourseRequest,
    MergeTabRequest,
    MoveTabRequest,
    OpenSessionRead,
    RestaurantTableRead,
    RoundCreate,
    SeatTableRequest,
    SessionRead,
    SessionRoundRead,
    SplitRequest,
    TablePaymentRead,
)
from app.schemas.time_entry import TimeEntryRead
from app.schemas.tips import CashUpRequest
from app.services.menu_service import MenuService
from app.services.payments import create_terminal_connection_token
from app.services.pos_service import PosService
from app.services.shift_service import ShiftService
from app.services.table_session_service import TableSessionService
from app.services.time_entry_service import TimeEntryService

router = APIRouter(prefix="/pos")

POS_GATE = [Depends(requires_feature_for_device("pos"))]  # device-token-only routes
POS_STAFF_GATE = [Depends(requires_feature_for_pos_staff("pos"))]  # pos_session-token routes


def get_pos_service(db: Annotated[Session, Depends(get_db)]) -> PosService:
    return PosService(db)


Pos = Annotated[PosService, Depends(get_pos_service)]


def get_shift_service(db: Annotated[Session, Depends(get_db)]) -> ShiftService:
    return ShiftService(db)


Shifts = Annotated[ShiftService, Depends(get_shift_service)]


def get_time_entry_service(db: Annotated[Session, Depends(get_db)]) -> TimeEntryService:
    return TimeEntryService(db)


TimeEntries = Annotated[TimeEntryService, Depends(get_time_entry_service)]


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


@router.get("/tables", response_model=list[RestaurantTableRead], dependencies=POS_GATE)
def list_tables(device: CurrentDevice, db: Annotated[Session, Depends(get_db)]) -> list[RestaurantTableRead]:
    """Every active table, for the POS's "pick a table to seat" view — device-only, just viewing the
    floor doesn't need to know who's using the till."""
    return TableSessionService(db).list_tables(device.device.restaurant_id)


@router.post("/tables/{table_id}/seat", response_model=OpenSessionRead, dependencies=POS_STAFF_GATE)
def seat_table(table_id: int, data: SeatTableRequest, staff: CurrentPosStaff, db: Annotated[Session, Depends(get_db)]) -> OpenSessionRead:
    """Staff seat a walk-in directly from the POS — no QR scan. Returns the same shape
    /pos/table-sessions/open already does, so the RN app's open-sessions list/UI needs no new type."""
    try:
        return TableSessionService(db).open_for_staff(table_id, staff.device.restaurant_id, data.party_size, data.tab_name)
    except AppError as exc:
        raise raise_http_for_app_error(exc) from exc


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


@router.get("/orders/awaiting-payment", response_model=list[AwaitingPaymentRead], dependencies=POS_STAFF_GATE)
def awaiting_payment(staff: CurrentPosStaff, service: Pos) -> list[AwaitingPaymentRead]:
    """Online pay-at-pickup / cash-on-delivery orders still owing money — where the till takes it."""
    return service.awaiting_payment(staff.device.restaurant_id)


@router.post("/orders/{order_id}/pay-cash", status_code=204, dependencies=POS_STAFF_GATE)
def pay_cash(order_id: int, staff: CurrentPosStaff, service: Pos) -> None:
    try:
        service.mark_counter_order_paid_cash(staff.device.restaurant_id, order_id, staff.user, staff.device.id)
    except (AppError, NotFoundError) as exc:
        raise raise_http_for_app_error(exc) from exc


@router.post("/orders/{order_id}/pay-card", response_model=PosCardIntentRead, dependencies=POS_STAFF_GATE)
def pay_card(order_id: int, staff: CurrentPosStaff, service: Pos) -> PosCardIntentRead:
    try:
        return service.create_counter_order_card_intent(staff.device.restaurant_id, order_id, staff.user, staff.device.id)
    except (AppError, NotFoundError) as exc:
        raise raise_http_for_app_error(exc) from exc


@router.post("/table-sessions/{session_id}/pay-card", response_model=TablePaymentRead, dependencies=POS_STAFF_GATE)
def pos_table_pay_card(
    session_id: int, staff: CurrentPosStaff, db: Annotated[Session, Depends(get_db)], split: SplitRequest | None = None,
) -> TablePaymentRead:
    session = db.get(TableSession, session_id)
    if session is None or session.restaurant_id != staff.device.restaurant_id:
        raise raise_http_for_app_error(NotFoundError("Session not found"))
    try:
        return TableSessionService(db).pay_by_card_at_pos(session_id, staff.device.restaurant_id, staff.user.id, staff.device.id, split)
    except AppError as exc:
        raise raise_http_for_app_error(exc) from exc


@router.post("/table-sessions/{session_id}/pay-cash", status_code=204, dependencies=POS_STAFF_GATE)
def pos_table_pay_cash(
    session_id: int, staff: CurrentPosStaff, db: Annotated[Session, Depends(get_db)], split: SplitRequest | None = None,
) -> None:
    """The cash-tender equivalent of pos_table_pay_card — was missing entirely until now, which meant a
    dine-in tab's cash could only be settled via the web admin, bypassing device_id/shift_id stamping
    and under-counting the till's Z-report. mark_paid_cash already does its own ownership/404 check via
    staff_session, so no redundant lookup here."""
    try:
        TableSessionService(db).mark_paid_cash(session_id, staff.device.restaurant_id, staff.user.id, staff.device.id, split)
    except (AppError, NotFoundError) as exc:
        raise raise_http_for_app_error(exc) from exc


@router.get("/table-sessions/{session_id}", response_model=SessionRead, dependencies=POS_STAFF_GATE)
def tab_detail(session_id: int, staff: CurrentPosStaff, db: Annotated[Session, Depends(get_db)]) -> SessionRead:
    """A tab with its rounds and lines (and their ids), for the staff view where lines are voided or comped."""
    tables = TableSessionService(db)
    try:
        return tables.view(tables.staff_session(session_id, staff.device.restaurant_id))
    except (AppError, NotFoundError) as exc:
        raise raise_http_for_app_error(exc) from exc


@router.post("/tabs", response_model=OpenSessionRead, status_code=201, dependencies=POS_STAFF_GATE)
def open_bar_tab(data: BarTabRequest, staff: CurrentPosStaff, db: Annotated[Session, Depends(get_db)]) -> OpenSessionRead:
    """Start a running tab with no table (a bar tab)."""
    try:
        return TableSessionService(db).open_bar_tab(staff.device.restaurant_id, data.name, data.party_size)
    except (AppError, NotFoundError) as exc:
        raise raise_http_for_app_error(exc) from exc


@router.post("/table-sessions/{session_id}/move", status_code=204, dependencies=POS_STAFF_GATE)
def pos_move_tab(session_id: int, data: MoveTabRequest, staff: CurrentPosStaff, db: Annotated[Session, Depends(get_db)]) -> None:
    """Move a party's tab to another table (they changed seats)."""
    try:
        TableSessionService(db).transfer(session_id, staff.device.restaurant_id, data.table_id)
    except (AppError, NotFoundError) as exc:
        raise raise_http_for_app_error(exc) from exc


@router.post("/table-sessions/{session_id}/merge", status_code=204, dependencies=POS_STAFF_GATE)
def pos_merge_tab(session_id: int, data: MergeTabRequest, staff: CurrentPosStaff, db: Annotated[Session, Depends(get_db)]) -> None:
    """Fold this tab into another open one."""
    try:
        TableSessionService(db).merge(session_id, data.into_session_id, staff.device.restaurant_id)
    except (AppError, NotFoundError) as exc:
        raise raise_http_for_app_error(exc) from exc


@router.post("/table-sessions/{session_id}/fire", response_model=FireCourseRead, dependencies=POS_STAFF_GATE)
def pos_fire_course(session_id: int, data: FireCourseRequest, staff: CurrentPosStaff, db: Annotated[Session, Depends(get_db)]) -> FireCourseRead:
    """Send a held course to the kitchen."""
    try:
        return FireCourseRead(fired=TableSessionService(db).fire_course(session_id, staff.device.restaurant_id, data.course, staff.user.id))
    except (AppError, NotFoundError) as exc:
        raise raise_http_for_app_error(exc) from exc


@router.get("/menu", response_model=MenuListResponse, dependencies=POS_STAFF_GATE)
def pos_menu(staff: CurrentPosStaff, db: Annotated[Session, Depends(get_db)]) -> MenuListResponse:
    """The whole menu for the till, sold-out dishes included (the public menu hides them, but the till needs to
    show them greyed out so a server can bring one back)."""
    return MenuService(db).list_items(restaurant_id=staff.device.restaurant_id, is_available=None, page=1, page_size=100, sort="popular")


@router.get("/customers", response_model=list[PosCustomerRead], dependencies=POS_STAFF_GATE)
def search_customers(staff: CurrentPosStaff, service: Pos, q: str = "") -> list[PosCustomerRead]:
    return service.search_customers(staff.device.restaurant_id, q)


@router.post("/coupons/preview", response_model=PosCouponPreviewRead, dependencies=POS_STAFF_GATE)
def preview_coupon(data: PosCouponPreviewRequest, staff: CurrentPosStaff, service: Pos) -> PosCouponPreviewRead:
    try:
        return service.preview_coupon(staff.device.restaurant_id, data)
    except (AppError, NotFoundError) as exc:
        raise raise_http_for_app_error(exc) from exc


@router.post("/menu-items/{item_id}/availability", response_model=AvailabilityRead, dependencies=POS_STAFF_GATE)
def set_availability(item_id: int, data: AvailabilityRequest, staff: CurrentPosStaff, service: Pos) -> AvailabilityRead:
    """86 a dish (or bring it back) from the till."""
    try:
        return service.set_item_availability(staff.user, staff.device.restaurant_id, item_id, data.is_available)
    except (AppError, NotFoundError) as exc:
        raise raise_http_for_app_error(exc) from exc


@router.post("/terminal/connection-token", response_model=PosConnectionTokenRead, dependencies=POS_STAFF_GATE)
def terminal_connection_token(staff: CurrentPosStaff, db: Annotated[Session, Depends(get_db)]) -> PosConnectionTokenRead:
    """What @stripe/stripe-terminal-react-native's tokenProvider calls. 503 under PAYMENT_PROVIDER=mock
    — there's no Terminal SDK session to authenticate without real Stripe, same "not configured" guard
    shape as POST /webhooks/stripe when STRIPE_WEBHOOK_SECRET is unset."""
    if settings.PAYMENT_PROVIDER.strip().lower() != "stripe":
        raise HTTPException(status_code=503, detail="Card payments are not configured")
    restaurant = db.get(Restaurant, staff.device.restaurant_id)
    if restaurant is None or not restaurant.stripe_account_id:
        raise HTTPException(status_code=503, detail="This restaurant hasn't connected a Stripe account yet")
    secret = create_terminal_connection_token(restaurant.stripe_account_id)
    return PosConnectionTokenRead(secret=secret)


@router.get("/shifts/current", response_model=ShiftRead | None, dependencies=POS_GATE)
def current_shift(device: CurrentDevice, service: Shifts) -> ShiftRead | None:
    return service.current_shift(device.device)


@router.post("/shifts/open", response_model=ShiftRead, status_code=201, dependencies=POS_STAFF_GATE)
def open_shift(data: ShiftOpenRequest, staff: CurrentPosStaff, service: Shifts) -> ShiftRead:
    try:
        return service.open_shift(staff.device, staff.user, data.starting_float)
    except AppError as exc:
        raise raise_http_for_app_error(exc) from exc


@router.get("/shifts/current/report", response_model=ShiftReportRead, dependencies=POS_STAFF_GATE)
def shift_x_report(staff: CurrentPosStaff, service: Shifts) -> ShiftReportRead:
    """X-report: where the till stands right now. Reads only — nothing is closed or reset."""
    try:
        return service.x_report(staff.device)
    except (AppError, NotFoundError) as exc:
        raise raise_http_for_app_error(exc) from exc


@router.post("/shifts/{shift_id}/close", response_model=ShiftReportRead, dependencies=POS_STAFF_GATE)
def close_shift(shift_id: int, data: ShiftCloseRequest, staff: CurrentPosStaff, service: Shifts) -> ShiftReportRead:
    try:
        return service.close_shift(staff.device, staff.user, shift_id, data.counted_cash, data.cash_tips)
    except (AppError, NotFoundError) as exc:
        raise raise_http_for_app_error(exc) from exc


@router.post("/shifts/{shift_id}/cash-movement", status_code=204, dependencies=POS_STAFF_GATE)
def cash_movement(shift_id: int, data: CashMovementCreate, staff: CurrentPosStaff, service: Shifts) -> None:
    try:
        service.record_cash_movement(staff.device, staff.user, data.kind, data.amount, data.reason)
    except AppError as exc:
        raise raise_http_for_app_error(exc) from exc


@router.get("/time-entries/current", response_model=TimeEntryRead | None, dependencies=POS_STAFF_GATE)
def current_time_entry(staff: CurrentPosStaff, service: TimeEntries) -> TimeEntryRead | None:
    # Per-person, not per-device — unlike /pos/shifts/current, this is POS_STAFF_GATE, not POS_GATE.
    return service.current_entry(staff.device.restaurant_id, staff.user)


@router.post("/time-entries/clock-in", response_model=TimeEntryRead, status_code=201, dependencies=POS_STAFF_GATE)
def clock_in(staff: CurrentPosStaff, service: TimeEntries) -> TimeEntryRead:
    try:
        return service.clock_in(staff.device.restaurant_id, staff.user, staff.device.id)
    except AppError as exc:
        raise raise_http_for_app_error(exc) from exc


@router.post("/time-entries/clock-out", response_model=TimeEntryRead, dependencies=POS_STAFF_GATE)
def clock_out(staff: CurrentPosStaff, service: TimeEntries, data: CashUpRequest | None = None) -> TimeEntryRead:
    """Clock out. A handheld server also sends their cash-up (cash on hand + cash tips); a till user just clocks out."""
    try:
        return service.clock_out(staff.device.restaurant_id, staff.user, data)
    except AppError as exc:
        raise raise_http_for_app_error(exc) from exc
