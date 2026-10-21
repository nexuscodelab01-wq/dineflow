"""Clock in/out and per-employee reporting schemas."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class TimeEntryRead(BaseModel):
    id: int
    clock_in_at: datetime
    clock_out_at: datetime | None
    # A server's cash-up at clock-out. expected_cash = cash they took in the window; variance nets off cash tips.
    counted_cash: Decimal | None = None
    cash_tips: Decimal = Decimal("0.00")
    expected_cash: Decimal = Decimal("0.00")
    variance: Decimal | None = None


class EmployeeReportRow(BaseModel):
    user_id: int
    name: str
    cash_total: Decimal
    card_total: Decimal
    order_count: int
    hours_worked: Decimal
    card_tips: Decimal = Decimal("0.00")
    cash_tips: Decimal = Decimal("0.00")
    # None when hours_worked is 0 — nothing to divide by, not a zero result.
    sales_per_labour_hour: Decimal | None
