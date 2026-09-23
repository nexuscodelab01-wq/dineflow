"""Waitlist (walk-in queue) Pydantic schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.enums import WaitlistStatus


class WaitlistCreate(BaseModel):
    guest_name: str = Field(min_length=1, max_length=200)
    guest_email: EmailStr | None = None
    guest_phone: str | None = Field(default=None, max_length=30)
    party_size: int = Field(ge=1, le=20)
    notes: str | None = Field(default=None, max_length=1000)
    quoted_minutes: int | None = Field(default=None, ge=0, le=240)


class WaitlistSeat(BaseModel):
    table_id: int
    duration_minutes: int = Field(default=90, ge=30, le=240)


class WaitlistRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    guest_name: str
    guest_email: str | None
    guest_phone: str | None
    party_size: int
    notes: str | None
    quoted_minutes: int | None
    status: WaitlistStatus
    notified_at: datetime | None
    reservation_id: int | None
    created_at: datetime
    # How long they've been waiting — computed by the service, not stored.
    waiting_minutes: int
