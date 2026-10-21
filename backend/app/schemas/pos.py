"""POS schemas: device pairing, PIN login, counter orders."""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.table_session import OpenSessionRead

DeviceKind = Literal["TILL", "HANDHELD"]


class DevicePairRequest(BaseModel):
    label: str = Field(min_length=1, max_length=100)
    kind: DeviceKind = "TILL"


class DevicePairResponse(BaseModel):
    device_id: int
    label: str
    kind: str
    device_token: str  # shown once — this is the pairing code the iPad is given


class DeviceRead(BaseModel):
    id: int
    label: str
    kind: str
    paired_by_label: str | None
    revoked_at: datetime | None
    last_seen_at: datetime | None
    created_at: datetime


class PinLoginRequest(BaseModel):
    pin: str = Field(min_length=4, max_length=8)


class PinLoginResponse(BaseModel):
    pos_session_token: str
    staff_name: str
    device_kind: str
    currency: str = "usd"
    country: str = "US"
    tips_enabled: bool = False
    expires_in: int  # seconds


class PosOrderCreate(BaseModel):
    items: list["PosOrderItemCreate"] = Field(min_length=1, max_length=40)
    notes: str | None = Field(default=None, max_length=500)


class PosOrderItemCreate(BaseModel):
    menu_item_id: int
    quantity: int = Field(ge=1, le=50)
    modifier_option_ids: list[int] = Field(default_factory=list)
    special_instructions: str | None = Field(default=None, max_length=500)


class PosOrderRead(BaseModel):
    order_id: int
    order_number: str
    total: Decimal
    status: str


class OpenTableSessionsResponse(BaseModel):
    sessions: list[OpenSessionRead]


class PosConnectionTokenRead(BaseModel):
    secret: str


class PosCardIntentRead(BaseModel):
    order_id: int
    status: str  # "CONFIRMED" (mock, settled synchronously) or "PENDING" (Stripe, webhook still pending)
    client_secret: str | None = None
    provider_intent_id: str | None = None
