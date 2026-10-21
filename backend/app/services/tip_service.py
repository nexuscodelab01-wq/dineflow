"""Tip reporting and allocation. Card tips come off the Payment (`tip_amount`, read back from Stripe), cash tips
are declared by staff at shift close / clock-out; both are attributed to the person who collected them. The
restaurant's pooling policy then decides what each person is paid, and `finalize` writes that down as an
immutable ledger so there is always a record of who got what and why."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.models.audit_log import AuditLog
from app.models.enums import PaymentStatus
from app.models.payment import Payment
from app.models.restaurant import Restaurant
from app.models.shift import Shift
from app.models.time_entry import TimeEntry
from app.models.tip_allocation import TipAllocation
from app.models.user import User
from app.schemas.tips import TipAllocationRead, TipReportRead, TipRow
from app.services.tax.base import allocate
from app.services.time_entry_service import TimeEntryService

ZERO = Decimal("0.00")


class TipService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------ building blocks

    def card_tips(self, restaurant_id: int, start: datetime, end: datetime) -> dict[int, Decimal]:
        rows = self.db.execute(
            select(Payment.staff_user_id, func.coalesce(func.sum(Payment.tip_amount), 0)).where(
                Payment.restaurant_id == restaurant_id, Payment.staff_user_id.is_not(None),
                Payment.status == PaymentStatus.COMPLETED, Payment.created_at >= start, Payment.created_at <= end,
            ).group_by(Payment.staff_user_id)
        ).all()
        return {uid: Decimal(total) for uid, total in rows if uid is not None and Decimal(total) > 0}

    def unassigned_tips(self, restaurant_id: int, start: datetime, end: datetime) -> Decimal:
        """Tips on payments nobody took at a till — i.e. added online by customers (delivery, pickup)."""
        return Decimal(self.db.scalar(
            select(func.coalesce(func.sum(Payment.tip_amount), 0)).where(
                Payment.restaurant_id == restaurant_id, Payment.staff_user_id.is_(None),
                Payment.status == PaymentStatus.COMPLETED, Payment.created_at >= start, Payment.created_at <= end,
            )
        ) or 0)

    def cash_tips(self, restaurant_id: int, start: datetime, end: datetime) -> dict[int, Decimal]:
        """Declared cash tips: a server's own at clock-out, plus a till closer's declaration at shift close."""
        out: dict[int, Decimal] = {}
        entries = self.db.execute(
            select(TimeEntry.user_id, func.coalesce(func.sum(TimeEntry.cash_tips), 0)).where(
                TimeEntry.restaurant_id == restaurant_id, TimeEntry.clock_out_at.is_not(None),
                TimeEntry.clock_out_at >= start, TimeEntry.clock_out_at <= end,
            ).group_by(TimeEntry.user_id)
        ).all()
        for uid, total in entries:
            out[uid] = out.get(uid, ZERO) + Decimal(total)
        shifts = self.db.execute(
            select(Shift.closed_by_user_id, func.coalesce(func.sum(Shift.cash_tips), 0)).where(
                Shift.restaurant_id == restaurant_id, Shift.closed_at.is_not(None), Shift.closed_by_user_id.is_not(None),
                Shift.closed_at >= start, Shift.closed_at <= end,
            ).group_by(Shift.closed_by_user_id)
        ).all()
        for uid, total in shifts:
            if uid is not None:
                out[uid] = out.get(uid, ZERO) + Decimal(total)
        return {uid: total for uid, total in out.items() if total > 0}

    # ------------------------------------------------------------------ report

    def report(self, restaurant_id: int, start: datetime, end: datetime) -> TipReportRead:
        restaurant = self.db.get(Restaurant, restaurant_id)
        if restaurant is None:
            raise NotFoundError("Restaurant not found")
        card = self.card_tips(restaurant_id, start, end)
        cash = self.cash_tips(restaurant_id, start, end)
        hours = TimeEntryService(self.db).hours_worked(restaurant_id, start, end)
        user_ids = sorted(set(card) | set(cash) | (set(hours) if restaurant.tip_pool_mode != "KEEP" else set()))
        names = {u.id: u.first_name for u in self.db.scalars(select(User).where(User.id.in_(user_ids)))} if user_ids else {}
        collected = {uid: card.get(uid, ZERO) + cash.get(uid, ZERO) for uid in user_ids}
        unassigned = self.unassigned_tips(restaurant_id, start, end)
        # Tips nobody collected (online orders) belong to the pot when tips are pooled; under "keep your own" they have no
        # owner and are reported separately for the restaurant to decide.
        pooled = restaurant.tip_pool_mode != "KEEP"
        total = sum(collected.values(), ZERO) + (unassigned if pooled else ZERO)
        payouts = self._payouts(restaurant.tip_pool_mode, user_ids, collected, hours, total)
        finalized = self.db.scalar(
            select(TipAllocation.id).where(
                TipAllocation.restaurant_id == restaurant_id, TipAllocation.period_start < end, TipAllocation.period_end > start,
            ).limit(1)
        ) is not None
        rows = [
            TipRow(
                user_id=uid, name=names.get(uid, "?"), card_tips=card.get(uid, ZERO), cash_tips=cash.get(uid, ZERO),
                collected=collected[uid], hours=hours.get(uid, ZERO), payout=payouts[uid],
            )
            for uid in user_ids
        ]
        return TipReportRead(mode=restaurant.tip_pool_mode, start=start, end=end, total=total, rows=rows, unassigned=unassigned, already_finalized=finalized)

    @staticmethod
    def _payouts(mode: str, user_ids: list[int], collected: dict[int, Decimal], hours: dict[int, Decimal], total: Decimal) -> dict[int, Decimal]:
        if mode == "KEEP" or not user_ids:
            return {uid: collected[uid] for uid in user_ids}
        weights = [hours.get(uid, ZERO) for uid in user_ids] if mode == "POOL_HOURS" else [Decimal(1)] * len(user_ids)
        if sum(weights, ZERO) <= 0:  # nobody clocked time: share equally rather than lose the pot
            weights = [Decimal(1)] * len(user_ids)
        return dict(zip(user_ids, allocate(total, weights), strict=True))

    # ------------------------------------------------------------------ ledger

    def finalize(self, restaurant_id: int, start: datetime, end: datetime, admin: User) -> TipReportRead:
        report = self.report(restaurant_id, start, end)
        if report.already_finalized:
            raise ConflictError("Part of this period has already been finalized")
        if not report.rows:
            raise AppError("There are no tips to allocate in this period")
        for row in report.rows:
            self.db.add(TipAllocation(
                restaurant_id=restaurant_id, user_id=row.user_id, period_start=start, period_end=end, mode=report.mode,
                collected=row.collected, amount=row.payout, hours=row.hours, finalized_by_user_id=admin.id,
            ))
        self.db.add(AuditLog(
            restaurant_id=restaurant_id, actor_user_id=admin.id, actor_label=admin.email, action="tips.finalized",
            target=f"{start.isoformat()}..{end.isoformat()}", details={"mode": report.mode, "total": str(report.total)},
        ))
        self.db.commit()
        report.already_finalized = True
        return report

    def history(self, restaurant_id: int, limit: int = 200) -> list[TipAllocationRead]:
        rows = self.db.execute(
            select(TipAllocation, User.first_name).join(User, User.id == TipAllocation.user_id)
            .where(TipAllocation.restaurant_id == restaurant_id).order_by(TipAllocation.id.desc()).limit(limit)
        ).all()
        return [
            TipAllocationRead(
                id=a.id, user_id=a.user_id, name=name, period_start=a.period_start, period_end=a.period_end, mode=a.mode,
                collected=a.collected, amount=a.amount, hours=a.hours, created_at=a.created_at,
            )
            for a, name in rows
        ]
