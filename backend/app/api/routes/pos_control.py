"""POS controls: approval by a manager's PIN, voids / comps / discounts / refunds, and the recent-payments list
a refund starts from. All behind the `pos` and `pos_controls` flags and a PIN'd-in staff member."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.core.exceptions import AppError, NotFoundError, raise_http_for_app_error
from app.db.session import get_db
from app.dependencies.features import requires_feature_for_pos_staff
from app.dependencies.pos import CurrentPosStaff
from app.schemas.pos_control import (
    AdjustmentResult,
    AuthorizeRead,
    AuthorizeRequest,
    CompRequest,
    DiscountRequest,
    ReasonsRead,
    RecentPaymentRead,
    RefundRequest,
    VoidRequest,
)
from app.schemas.table_session import SessionRead
from app.services.pos_control_service import PosControlService
from app.services.table_session_service import TableSessionService

GATE = [Depends(requires_feature_for_pos_staff("pos")), Depends(requires_feature_for_pos_staff("pos_controls"))]
router = APIRouter(prefix="/pos", dependencies=GATE)


def get_service(db: Annotated[Session, Depends(get_db)]) -> PosControlService:
    return PosControlService(db)


Service = Annotated[PosControlService, Depends(get_service)]
Override = Annotated[str | None, Header(alias="X-Manager-Override")]


def _run(call):
    try:
        return call()
    except (AppError, NotFoundError) as exc:
        raise raise_http_for_app_error(exc) from exc


@router.get("/reasons", response_model=ReasonsRead)
def reasons(_: CurrentPosStaff, service: Service) -> ReasonsRead:
    return service.reasons()


@router.post("/authorize", response_model=AuthorizeRead)
def authorize(data: AuthorizeRequest, staff: CurrentPosStaff, service: Service) -> AuthorizeRead:
    """A manager enters their own PIN to approve one action for the person holding the device."""
    return _run(lambda: service.authorize(staff.device, data.pin, data.action))


@router.get("/table-sessions/{session_id}", response_model=SessionRead)
def tab_detail(session_id: int, staff: CurrentPosStaff, db: Annotated[Session, Depends(get_db)]) -> SessionRead:
    """A tab with its rounds and lines (and their ids), for the staff view where lines are voided or comped."""
    tables = TableSessionService(db)
    return _run(lambda: tables.view(tables.staff_session(session_id, staff.device.restaurant_id)))


@router.post("/order-items/{item_id}/void", response_model=AdjustmentResult)
def void_item(item_id: int, data: VoidRequest, staff: CurrentPosStaff, service: Service, override: Override = None) -> AdjustmentResult:
    return _run(lambda: service.void_item(staff, item_id, data.quantity, data.reason_code, data.note, override))


@router.post("/order-items/{item_id}/comp", response_model=AdjustmentResult)
def comp_item(item_id: int, data: CompRequest, staff: CurrentPosStaff, service: Service, override: Override = None) -> AdjustmentResult:
    return _run(lambda: service.comp_item(staff, item_id, data.reason_code, data.note, override))


@router.post("/order-items/{item_id}/discount", response_model=AdjustmentResult)
def discount_item(item_id: int, data: DiscountRequest, staff: CurrentPosStaff, service: Service, override: Override = None) -> AdjustmentResult:
    return _run(lambda: service.discount_item(staff, item_id, data, override))


@router.post("/orders/{order_id}/discount", response_model=AdjustmentResult)
def discount_order(order_id: int, data: DiscountRequest, staff: CurrentPosStaff, service: Service, override: Override = None) -> AdjustmentResult:
    return _run(lambda: service.discount_order(staff, order_id, data, override))


@router.post("/table-sessions/{session_id}/discount", response_model=AdjustmentResult)
def discount_tab(session_id: int, data: DiscountRequest, staff: CurrentPosStaff, service: Service, override: Override = None) -> AdjustmentResult:
    return _run(lambda: service.discount_session(staff, session_id, data, override))


@router.get("/recent-payments", response_model=list[RecentPaymentRead])
def recent_payments(staff: CurrentPosStaff, service: Service) -> list[RecentPaymentRead]:
    return service.recent_payments(staff)


@router.post("/orders/{order_id}/refund", response_model=AdjustmentResult)
def refund_order(order_id: int, data: RefundRequest, staff: CurrentPosStaff, service: Service, override: Override = None) -> AdjustmentResult:
    return _run(lambda: service.refund_order(staff, order_id, data.reason_code, data.note, override))


@router.post("/table-sessions/{session_id}/refund", response_model=AdjustmentResult)
def refund_tab(session_id: int, data: RefundRequest, staff: CurrentPosStaff, service: Service, override: Override = None) -> AdjustmentResult:
    return _run(lambda: service.refund_session(staff, session_id, data.reason_code, data.note, override))
