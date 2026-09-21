"""QR table ordering schemas."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.order import OrderItemCreate


class TableInfo(BaseModel):
    """What the QR page learns from the token before anyone joins."""

    restaurant_id: int
    restaurant_name: str
    table_number: str
    ordering_open: bool
    reason: str | None = None  # why ordering is closed, in words a guest can act on


class JoinRequest(BaseModel):
    name: str | None = Field(default=None, max_length=80)


class JoinResponse(BaseModel):
    access_token: str
    session_id: int
    guest_id: int


class RoundCreate(BaseModel):
    items: list[OrderItemCreate] = Field(min_length=1, max_length=40)
    notes: str | None = Field(default=None, max_length=500)


class SessionItemRead(BaseModel):
    name: str
    quantity: int
    line_total: Decimal
    special_instructions: str | None = None
    options: list[str] = Field(default_factory=list)


class SessionRoundRead(BaseModel):
    order_id: int
    order_number: str
    round_no: int | None
    status: str
    total: Decimal
    ordered_by: str | None
    created_at: datetime
    items: list[SessionItemRead]


class SessionRead(BaseModel):
    session_id: int
    restaurant_id: int
    restaurant_name: str
    table_number: str
    guests: list[str]
    rounds: list[SessionRoundRead]
    total: Decimal  # everything ordered so far, excluding cancelled rounds


# ---- staff -------------------------------------------------------------------------------------

class QrTableRead(BaseModel):
    table_id: int
    table_number: str
    zone: str | None
    qr_token: str
    has_open_session: bool


class OpenSessionRead(BaseModel):
    session_id: int
    table_id: int
    table_number: str
    opened_at: datetime
    guests: int
    rounds: int
    total: Decimal
