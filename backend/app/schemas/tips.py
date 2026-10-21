"""Tip reporting and allocation schemas."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator


class TipRange(BaseModel):
    start: datetime
    end: datetime

    @model_validator(mode="after")
    def _ordered(self) -> "TipRange":
        if self.end <= self.start:
            raise ValueError("The end of the period must be after its start")
        return self


class TipRow(BaseModel):
    user_id: int
    name: str
    card_tips: Decimal
    cash_tips: Decimal
    collected: Decimal  # card + cash this person took themselves
    hours: Decimal
    payout: Decimal  # what the restaurant's policy pays them


class TipReportRead(BaseModel):
    mode: str
    start: datetime
    end: datetime
    total: Decimal
    rows: list[TipRow]
    unassigned: Decimal = Decimal("0.00")  # online tips with no server to credit (shared out only when tips are pooled)
    already_finalized: bool = False


class TipAllocationRead(BaseModel):
    id: int
    user_id: int
    name: str
    period_start: datetime
    period_end: datetime
    mode: str
    collected: Decimal
    amount: Decimal
    hours: Decimal
    created_at: datetime


class TerminalSyncRead(BaseModel):
    location_id: str | None
    configuration_id: str | None
    tipping: bool


class CashUpRequest(BaseModel):
    """A server's cash-up at clock-out: cash on hand, and how much of it is their cash tips."""

    counted_cash: Decimal = Field(ge=0)
    cash_tips: Decimal = Field(default=Decimal("0.00"), ge=0)
