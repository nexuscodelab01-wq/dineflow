"""Server-driven card reader schemas."""

from pydantic import BaseModel, Field

from app.schemas.table_session import SplitRequest


class ReaderRead(BaseModel):
    id: str
    label: str
    status: str
    device_type: str | None = None
    test_mode: bool = False  # Stripe test keys: a card tap can be simulated


class ReaderRegister(BaseModel):
    registration_code: str = Field(min_length=3, max_length=60)
    label: str = Field(min_length=1, max_length=60)


class PayOnReaderRequest(BaseModel):
    reader_id: str = Field(min_length=3, max_length=64)
    split: SplitRequest | None = None


class PaymentStatusRead(BaseModel):
    payment_id: int
    status: str
    failure_message: str | None = None
    tip_amount: str = "0.00"
    closed: bool = False  # for a tab: the whole bill is now settled
