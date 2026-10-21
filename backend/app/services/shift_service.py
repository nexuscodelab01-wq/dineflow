"""Till shifts and cash reconciliation (Z-report).

A shift is scoped to one physical Device (a till), not one staff member — multiple staff can PIN-switch
during a single open shift; it tracks who opened and who closed it, not who's currently logged in. This
is why `Payment` carries its own `shift_id` rather than this module reconstructing "what was taken during
this shift" from a `restaurant_id` + time-window query: two devices at one restaurant can have concurrent
open shifts, and a time-window-only query would mix their cash together. `shift_id` gives exact per-till
attribution regardless of concurrency — every POS cash/card tender stamps it (see pos_service.py /
table_session_service.py), and this module reads it back out.

Expected cash = starting_float + (cash taken during the shift) + (net cash movements, paid-in minus
paid-out). Variance = counted_cash (entered at close) - expected_cash. Card totals are informational only
— card payments never touch the physical drawer, so they're reported but play no part in the variance.

Known limitation: refunds aren't accounted for in this version — `OrderService.refund_payment` and
`TableSessionService.refund_tab` don't stamp `shift_id` and aren't touched here. A refund during an open
shift won't reduce its expected cash. Worth fixing before this is relied on for real accounting, not
silently worked around now.

Mandatory shift-open (no taking orders without one) is enforced client-side only, in the POS app's own
navigation — nothing here blocks a cash/card tender from happening with no open shift; `Payment.shift_id`
is simply left NULL in that case. This keeps every existing POS order/payment test passing unchanged.
"""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.models.audit_log import AuditLog
from app.models.cash_movement import CashMovement
from app.models.device import HANDHELD, Device
from app.models.enums import CashMovementKind, PaymentMethod, PaymentStatus
from app.models.payment import Payment
from app.models.shift import CLOSED, OPEN, Shift
from app.models.user import User
from app.schemas.shift import ShiftRead, ShiftReportRead
from app.services.feature_service import FeatureService

FEATURE = "pos"


class ShiftService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def current_shift_id(self, device_id: int | None) -> int | None:
        """The one shared lookup every Payment-creating POS method calls to decide what to stamp on a
        new Payment row. None in, None out — callers with no device (a non-POS caller) skip this."""
        if device_id is None:
            return None
        return self.db.scalar(select(Shift.id).where(Shift.device_id == device_id, Shift.state == OPEN))

    def current_shift(self, device: Device) -> ShiftRead | None:
        shift = self.db.scalar(select(Shift).where(Shift.device_id == device.id, Shift.state == OPEN))
        return self._read(shift) if shift else None

    def open_shift(self, device: Device, staff_user: User, starting_float: Decimal) -> ShiftRead:
        FeatureService(self.db).require(device.restaurant_id, FEATURE)
        if device.kind == HANDHELD:
            raise AppError("A handheld has no cash drawer, so it doesn't open a shift")
        if self.current_shift_id(device.id) is not None:
            raise ConflictError("This till already has an open shift")
        try:
            with self.db.begin_nested():
                shift = Shift(
                    restaurant_id=device.restaurant_id, device_id=device.id,
                    opened_by_user_id=staff_user.id, starting_float=starting_float,
                )
                self.db.add(shift)
                self.db.flush()
        except IntegrityError:  # two near-simultaneous opens on the same till
            raise ConflictError("This till already has an open shift") from None
        self.db.add(AuditLog(
            restaurant_id=device.restaurant_id, actor_user_id=staff_user.id, actor_label=staff_user.email,
            action="pos.shift_opened", target=f"shift:{shift.id}", details={"starting_float": str(starting_float)},
        ))
        self.db.commit()
        return self._read(shift)

    def record_cash_movement(self, device: Device, staff_user: User, kind: CashMovementKind, amount: Decimal, reason: str) -> None:
        shift = self._open_shift_or_error(device)
        if amount <= Decimal("0.00"):
            raise AppError("Enter an amount greater than zero")
        self.db.add(CashMovement(
            restaurant_id=device.restaurant_id, shift_id=shift.id, kind=kind, amount=amount,
            reason=reason, staff_user_id=staff_user.id,
        ))
        self.db.add(AuditLog(
            restaurant_id=device.restaurant_id, actor_user_id=staff_user.id, actor_label=staff_user.email,
            action="pos.cash_movement", target=f"shift:{shift.id}",
            details={"kind": kind.value, "amount": str(amount), "reason": reason},
        ))
        self.db.commit()

    def close_shift(self, device: Device, staff_user: User, shift_id: int, counted_cash: Decimal, cash_tips: Decimal = Decimal("0.00")) -> ShiftReportRead:
        shift = self._open_shift_or_error(device)
        if shift.id != shift_id:
            raise NotFoundError("Shift not found")
        cash_total, card_total, order_count = self._totals(shift.id)
        expected_cash = shift.starting_float + cash_total + self._cash_movements_net(shift.id)
        shift.state = CLOSED
        shift.closed_at = datetime.now(UTC)
        shift.closed_by_user_id = staff_user.id
        shift.counted_cash = counted_cash
        shift.cash_tips = cash_tips
        # Cash tips are in the drawer but aren't the house's: they don't count as a surplus.
        variance = counted_cash - cash_tips - expected_cash
        self.db.add(AuditLog(
            restaurant_id=device.restaurant_id, actor_user_id=staff_user.id, actor_label=staff_user.email,
            action="pos.shift_closed", target=f"shift:{shift.id}",
            details={"expected_cash": str(expected_cash), "counted_cash": str(counted_cash), "variance": str(variance)},
        ))
        self.db.commit()
        return ShiftReportRead(
            shift_id=shift.id, opened_at=shift.opened_at, opened_by=shift.opened_by.first_name if shift.opened_by else None,
            closed_at=shift.closed_at, closed_by=shift.closed_by.first_name if shift.closed_by else None,
            starting_float=shift.starting_float, cash_total=cash_total, card_total=card_total,
            order_count=order_count, expected_cash=expected_cash, counted_cash=counted_cash, variance=variance,
            card_tips=self._card_tips(shift.id), cash_tips=cash_tips,
        )

    def list_shifts(self, restaurant_id: int) -> list[ShiftReportRead]:
        shifts = self.db.scalars(
            select(Shift).where(Shift.restaurant_id == restaurant_id).order_by(Shift.opened_at.desc())
        ).all()
        out = []
        for shift in shifts:
            cash_total, card_total, order_count = self._totals(shift.id)
            expected_cash = shift.starting_float + cash_total + self._cash_movements_net(shift.id)
            variance = (shift.counted_cash - shift.cash_tips - expected_cash) if shift.counted_cash is not None else None
            out.append(ShiftReportRead(
                shift_id=shift.id, opened_at=shift.opened_at, opened_by=shift.opened_by.first_name if shift.opened_by else None,
                closed_at=shift.closed_at, closed_by=shift.closed_by.first_name if shift.closed_by else None,
                starting_float=shift.starting_float, cash_total=cash_total, card_total=card_total,
                order_count=order_count, expected_cash=expected_cash, counted_cash=shift.counted_cash, variance=variance,
                card_tips=self._card_tips(shift.id), cash_tips=shift.cash_tips,
            ))
        return out

    # ------------------------------------------------------------------ private helpers

    def _open_shift_or_error(self, device: Device) -> Shift:
        shift = self.db.scalar(select(Shift).where(Shift.device_id == device.id, Shift.state == OPEN))
        if shift is None:
            raise AppError("This till has no open shift")
        return shift

    def _totals(self, shift_id: int) -> tuple[Decimal, Decimal, int]:
        """Mirrors AnalyticsRepository._revenue's filter shape (Payment queried directly, status ==
        COMPLETED) but keyed on shift_id instead of a restaurant/date-range — see module docstring.
        card_total only sums PaymentMethod.CARD: POS card tenders are always CARD, never MOCK (MOCK is
        only the guest's own online-card fallback in TableSessionService.pay, irrelevant here)."""
        cash_total = self.db.scalar(select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.shift_id == shift_id, Payment.status == PaymentStatus.COMPLETED, Payment.payment_method == PaymentMethod.CASH,
        )) or Decimal("0.00")
        card_total = self.db.scalar(select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.shift_id == shift_id, Payment.status == PaymentStatus.COMPLETED, Payment.payment_method == PaymentMethod.CARD,
        )) or Decimal("0.00")
        order_count = self.db.scalar(select(func.count(Payment.id)).where(
            Payment.shift_id == shift_id, Payment.status == PaymentStatus.COMPLETED,
        )) or 0
        return cash_total, card_total, order_count

    def _card_tips(self, shift_id: int) -> Decimal:
        return self.db.scalar(select(func.coalesce(func.sum(Payment.tip_amount), 0)).where(
            Payment.shift_id == shift_id, Payment.status == PaymentStatus.COMPLETED,
        )) or Decimal("0.00")

    def _cash_movements_net(self, shift_id: int) -> Decimal:
        rows = self.db.execute(
            select(CashMovement.kind, func.coalesce(func.sum(CashMovement.amount), 0))
            .where(CashMovement.shift_id == shift_id).group_by(CashMovement.kind)
        ).all()
        net = Decimal("0.00")
        for kind, total in rows:
            net += Decimal(total) if kind == CashMovementKind.PAID_IN else -Decimal(total)
        return net

    def _read(self, shift: Shift) -> ShiftRead:
        return ShiftRead(
            shift_id=shift.id, state=shift.state, opened_at=shift.opened_at,
            opened_by=shift.opened_by.first_name if shift.opened_by else None,
            starting_float=shift.starting_float,
        )
