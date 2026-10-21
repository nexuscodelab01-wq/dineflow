"""POS control schemas: manager approval, voids / comps / discounts / refunds, and the adjustments report."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator


class AuthorizeRequest(BaseModel):
    pin: str = Field(min_length=4, max_length=8)
    action: str


class AuthorizeRead(BaseModel):
    token: str
    approver: str
    expires_in: int


class ReasonRead(BaseModel):
    code: str
    label: str


class ReasonsRead(BaseModel):
    VOID: list[ReasonRead]
    COMP: list[ReasonRead]
    DISCOUNT: list[ReasonRead]
    REFUND: list[ReasonRead]


class AdjustBase(BaseModel):
    reason_code: str = Field(min_length=1, max_length=30)
    note: str | None = Field(default=None, max_length=300)


class VoidRequest(AdjustBase):
    # How many of the line to remove; omitted = the whole line.
    quantity: int | None = Field(default=None, ge=1)


class CompRequest(AdjustBase):
    pass


class DiscountRequest(AdjustBase):
    percent: Decimal | None = Field(default=None, gt=0, le=100)
    amount: Decimal | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _one_of(self) -> "DiscountRequest":
        if (self.percent is None) == (self.amount is None):
            raise ValueError("Give either a percentage or an amount")
        return self


class RefundRequest(AdjustBase):
    pass


class AdjustmentResult(BaseModel):
    adjustment_id: int
    amount: Decimal
    order_total: Decimal | None = None  # the order's new total after a void / comp / discount


class AdjustmentRead(BaseModel):
    id: int
    kind: str
    amount: Decimal
    reason_code: str
    note: str | None
    order_number: str | None
    staff: str | None
    authorized_by: str | None
    created_at: datetime
    detail: dict


class RecentPaymentRead(BaseModel):
    """Something that was paid recently and could be refunded."""

    kind: str  # ORDER | TAB
    id: int
    label: str
    amount: Decimal
    method: str
    paid_at: datetime
    refundable: bool
