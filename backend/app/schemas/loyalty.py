"""Loyalty points Pydantic schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import LoyaltyReason


class LoyaltyTransactionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: int | None
    points: int
    reason: LoyaltyReason
    note: str | None
    created_at: datetime


class LoyaltyAccountRead(BaseModel):
    balance: int
    points_per_currency: int
    transactions: list[LoyaltyTransactionRead]


class AdminLoyaltyAccountRead(BaseModel):
    user_id: int
    name: str
    email: str
    balance: int


class LoyaltyAdjust(BaseModel):
    points: int = Field(description="Positive to add, negative to deduct")
    note: str | None = Field(default=None, max_length=500)

    @field_validator("points")
    @classmethod
    def _not_zero(cls, value: int) -> int:
        if value == 0:
            raise ValueError("points can't be zero")
        return value
