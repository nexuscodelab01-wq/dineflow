"""Shift / cash-reconciliation (Z-report) schemas."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.enums import CashMovementKind


class ShiftOpenRequest(BaseModel):
    starting_float: Decimal = Field(ge=0)


class ShiftRead(BaseModel):
    shift_id: int
    state: str
    opened_at: datetime
    opened_by: str | None
    starting_float: Decimal


class ShiftCloseRequest(BaseModel):
    counted_cash: Decimal = Field(ge=0)


class ShiftReportRead(BaseModel):
    shift_id: int
    opened_at: datetime
    opened_by: str | None
    closed_at: datetime | None
    closed_by: str | None
    starting_float: Decimal
    cash_total: Decimal
    card_total: Decimal
    order_count: int
    expected_cash: Decimal
    counted_cash: Decimal | None
    variance: Decimal | None


class CashMovementCreate(BaseModel):
    kind: CashMovementKind
    amount: Decimal = Field(gt=0)
    reason: str = Field(min_length=1, max_length=300)
