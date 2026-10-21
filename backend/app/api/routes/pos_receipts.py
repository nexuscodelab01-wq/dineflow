"""Receipts at the till: the receipt as data, as printer bytes, and emailed to the customer."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.exceptions import AppError, NotFoundError, raise_http_for_app_error
from app.db.session import get_db
from app.dependencies.features import requires_feature_for_pos_staff
from app.dependencies.pos import CurrentPosStaff
from app.schemas.receipt import EmailReceiptRequest, EscPosRead, Receipt
from app.services.receipt_service import ReceiptService

router = APIRouter(prefix="/pos", dependencies=[Depends(requires_feature_for_pos_staff("pos"))])


def get_service(db: Annotated[Session, Depends(get_db)]) -> ReceiptService:
    return ReceiptService(db)


Service = Annotated[ReceiptService, Depends(get_service)]


def _run(call):
    try:
        return call()
    except (AppError, NotFoundError) as exc:
        raise raise_http_for_app_error(exc) from exc


@router.get("/orders/{order_id}/receipt", response_model=Receipt)
def order_receipt(order_id: int, staff: CurrentPosStaff, service: Service) -> Receipt:
    return _run(lambda: service.for_order(staff.device.restaurant_id, order_id))


@router.get("/table-sessions/{session_id}/receipt", response_model=Receipt)
def tab_receipt(session_id: int, staff: CurrentPosStaff, service: Service) -> Receipt:
    """A tab's check (while it's open) or receipt (once paid)."""
    return _run(lambda: service.for_session(staff.device.restaurant_id, session_id))


@router.get("/orders/{order_id}/receipt/escpos", response_model=EscPosRead)
def order_receipt_bytes(order_id: int, staff: CurrentPosStaff, service: Service, kick: bool = False, width: Annotated[int, Query(ge=24, le=64)] = 42) -> EscPosRead:
    receipt = _run(lambda: service.for_order(staff.device.restaurant_id, order_id))
    return service.escpos(receipt, width=width, drawer_kick=kick and staff.device.cash_drawer)


@router.get("/table-sessions/{session_id}/receipt/escpos", response_model=EscPosRead)
def tab_receipt_bytes(session_id: int, staff: CurrentPosStaff, service: Service, kick: bool = False, width: Annotated[int, Query(ge=24, le=64)] = 42) -> EscPosRead:
    receipt = _run(lambda: service.for_session(staff.device.restaurant_id, session_id))
    return service.escpos(receipt, width=width, drawer_kick=kick and staff.device.cash_drawer)


@router.post("/orders/{order_id}/receipt/email", status_code=204)
def email_order_receipt(order_id: int, data: EmailReceiptRequest, staff: CurrentPosStaff, service: Service) -> None:
    receipt = _run(lambda: service.for_order(staff.device.restaurant_id, order_id))
    _run(lambda: service.email(staff.device.restaurant_id, receipt, str(data.email), f"receipt:order:{order_id}:{data.email}"))


@router.post("/table-sessions/{session_id}/receipt/email", status_code=204)
def email_tab_receipt(session_id: int, data: EmailReceiptRequest, staff: CurrentPosStaff, service: Service) -> None:
    receipt = _run(lambda: service.for_session(staff.device.restaurant_id, session_id))
    _run(lambda: service.email(staff.device.restaurant_id, receipt, str(data.email), f"receipt:tab:{session_id}:{data.email}"))
