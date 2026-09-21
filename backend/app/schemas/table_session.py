"""QR table ordering schemas."""

from datetime import datetime
from decimal import Decimal

from typing import Literal

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
    requests: list[str] = Field(default_factory=list)  # kinds the table has asked for and staff haven't answered yet


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
    requests: list[str] = Field(default_factory=list)


class RequestCreate(BaseModel):
    kind: Literal["WAITER", "BILL"]


class ServiceRequestStaffRead(BaseModel):
    id: int
    session_id: int
    table_id: int
    table_number: str
    kind: str
    asked_by: str | None
    created_at: datetime


# ---- waiter view ---------------------------------------------------------------------------------

class WaiterSessionRead(BaseModel):
    session_id: int
    opened_at: datetime
    guests: int
    rounds: int
    ready_rounds: int  # rounds the kitchen has finished that nobody has served yet
    total: Decimal  # with tax, excluding cancelled rounds
    requests: list[str] = Field(default_factory=list)
    waiting_since: datetime | None = None  # the oldest unanswered request


class WaiterTableRead(BaseModel):
    table_id: int
    table_number: str
    capacity: int
    zone: str | None
    shape: str
    pos_x: float | None
    pos_y: float | None
    status: str
    session: WaiterSessionRead | None = None


class TransferRequest(BaseModel):
    table_id: int
