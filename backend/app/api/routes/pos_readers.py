"""Server-driven card readers at the till (WisePOS E / S700): list them, charge one, follow the payment, cancel."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.exceptions import AppError, NotFoundError, raise_http_for_app_error
from app.db.session import get_db
from app.dependencies.features import requires_feature_for_pos_staff
from app.dependencies.pos import CurrentPosStaff
from app.models.enums import PaymentStatus
from app.models.payment import Payment
from app.models.table_session import CLOSED as SESSION_CLOSED
from app.models.table_session import TableSession
from app.schemas.pos import PosCardIntentRead
from app.schemas.reader import PaymentStatusRead, PayOnReaderRequest, ReaderRead
from app.schemas.table_session import TablePaymentRead
from app.services.pos_service import PosService
from app.services.reader_service import ReaderService
from app.services.table_session_service import TableSessionService

router = APIRouter(prefix="/pos", dependencies=[Depends(requires_feature_for_pos_staff("pos"))])


def _run(call):
    try:
        return call()
    except (AppError, NotFoundError) as exc:
        raise raise_http_for_app_error(exc) from exc


@router.get("/readers", response_model=list[ReaderRead])
def readers(staff: CurrentPosStaff, db: Annotated[Session, Depends(get_db)]) -> list[ReaderRead]:
    return ReaderService(db).list_readers(staff.device.restaurant_id)


@router.post("/orders/{order_id}/pay-reader", response_model=PosCardIntentRead)
def pay_order_on_reader(order_id: int, data: PayOnReaderRequest, staff: CurrentPosStaff, db: Annotated[Session, Depends(get_db)]) -> PosCardIntentRead:
    rid = staff.device.restaurant_id
    _run(lambda: ReaderService(db).require(rid, data.reader_id))
    return _run(lambda: PosService(db).create_counter_order_card_intent(rid, order_id, staff.user, staff.device.id, reader_id=data.reader_id))


@router.post("/table-sessions/{session_id}/pay-reader", response_model=TablePaymentRead)
def pay_tab_on_reader(session_id: int, data: PayOnReaderRequest, staff: CurrentPosStaff, db: Annotated[Session, Depends(get_db)]) -> TablePaymentRead:
    rid = staff.device.restaurant_id
    _run(lambda: ReaderService(db).require(rid, data.reader_id))
    return _run(lambda: TableSessionService(db).pay_by_card_at_pos(session_id, rid, staff.user.id, staff.device.id, data.split, reader_id=data.reader_id))


@router.post("/readers/{reader_id}/cancel", status_code=204)
def cancel_reader(reader_id: str, staff: CurrentPosStaff, db: Annotated[Session, Depends(get_db)]) -> None:
    """Stop the reader and free this person's unfinished card payments so the sale can be retried."""
    _run(lambda: ReaderService(db).cancel(staff.device.restaurant_id, staff.user.id, reader_id))


@router.post("/readers/{reader_id}/simulate-tap", status_code=204)
def simulate_tap(reader_id: str, staff: CurrentPosStaff, db: Annotated[Session, Depends(get_db)]) -> None:
    """Test mode: pretend a customer tapped a test card on this simulated reader."""
    _run(lambda: ReaderService(db).simulate_tap(staff.device.restaurant_id, reader_id))


@router.get("/payments/{payment_id}", response_model=PaymentStatusRead)
def payment_status(payment_id: int, staff: CurrentPosStaff, db: Annotated[Session, Depends(get_db)]) -> PaymentStatusRead:
    """Poll a card payment the reader is taking: PENDING until it finishes, then COMPLETED or FAILED."""
    payment = db.get(Payment, payment_id)
    if payment is None or payment.restaurant_id != staff.device.restaurant_id:
        raise raise_http_for_app_error(NotFoundError("Payment not found"))
    closed = False
    if payment.table_session_id is not None:
        session = db.get(TableSession, payment.table_session_id)
        closed = session is not None and session.state == SESSION_CLOSED
    return PaymentStatusRead(
        payment_id=payment.id, status=payment.status.value if isinstance(payment.status, PaymentStatus) else str(payment.status),
        failure_message=payment.failure_message, tip_amount=str(payment.tip_amount), closed=closed,
    )
