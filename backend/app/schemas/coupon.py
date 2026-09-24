"""Coupon Pydantic schemas."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.enums import CouponDiscountType


class CouponBase(BaseModel):
    code: str = Field(min_length=3, max_length=40)
    description: str | None = Field(default=None, max_length=200)
    discount_type: CouponDiscountType
    discount_value: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    min_order_amount: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    max_discount_amount: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    max_redemptions: int | None = Field(default=None, ge=1)
    max_per_customer: int | None = Field(default=None, ge=1)

    @field_validator("code")
    @classmethod
    def _normalize_code(cls, value: str) -> str:
        """Stored upper-cased and stripped, so "save10", " SAVE10 " and "SAVE10" are one coupon."""
        code = value.strip().upper()
        if not code.isalnum():
            raise ValueError("A code can only contain letters and numbers")
        return code

    @model_validator(mode="after")
    def _check_rules(self) -> "CouponBase":
        if self.discount_type == CouponDiscountType.PERCENT and self.discount_value > 100:
            raise ValueError("A percentage discount can't be more than 100%")
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValueError("The end date must be after the start date")
        return self


class CouponCreate(CouponBase):
    pass


class CouponUpdate(BaseModel):
    """Everything except the code, which is what customers have already been told."""

    description: str | None = Field(default=None, max_length=200)
    discount_type: CouponDiscountType | None = None
    discount_value: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    min_order_amount: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    max_discount_amount: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    max_redemptions: int | None = Field(default=None, ge=1)
    max_per_customer: int | None = Field(default=None, ge=1)
    is_active: bool | None = None


class CouponRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    description: str | None
    discount_type: CouponDiscountType
    discount_value: Decimal
    min_order_amount: Decimal | None
    max_discount_amount: Decimal | None
    starts_at: datetime | None
    ends_at: datetime | None
    max_redemptions: int | None
    max_per_customer: int | None
    times_redeemed: int
    is_active: bool
    created_at: datetime


class CouponPreviewRequest(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    subtotal: Decimal = Field(ge=0, max_digits=10, decimal_places=2)


class CouponPreviewResponse(BaseModel):
    """Advisory only — what the customer is shown before checkout. The binding number is worked out
    again when the order is actually placed, from the server's own subtotal."""

    code: str
    description: str | None
    discount: Decimal
