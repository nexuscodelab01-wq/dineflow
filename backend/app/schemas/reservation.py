"""Reservation Pydantic schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.enums import ReservationStatus


class ReservationCreate(BaseModel):
    table_id: int
    party_size: int = Field(ge=1, le=20)
    starts_at: datetime
    duration_minutes: int = Field(default=90, ge=30, le=240)
    guest_name: str = Field(min_length=1, max_length=200)
    guest_email: EmailStr | None = None
    guest_phone: str | None = Field(default=None, max_length=30)
    notes: str | None = Field(default=None, max_length=1000)
    hold: bool = False  # True = soft hold (expires); False = confirm immediately


class AdminReservationCreate(ReservationCreate):
    user_id: int | None = None
    seat_immediately: bool = False


class ReservationStatusUpdate(BaseModel):
    status: ReservationStatus
    notes: str | None = Field(default=None, max_length=1000)


class ReservationExtend(BaseModel):
    """Give seated guests more time (they're running over)."""

    minutes: int = Field(ge=5, le=120)


class ReservationUpdate(BaseModel):
    """Admin edit / reschedule of an upcoming reservation. Omitted fields are unchanged."""

    table_id: int | None = None
    party_size: int | None = Field(default=None, ge=1, le=20)
    starts_at: datetime | None = None
    duration_minutes: int | None = Field(default=None, ge=30, le=240)
    guest_name: str | None = Field(default=None, min_length=1, max_length=200)
    guest_email: EmailStr | None = None
    guest_phone: str | None = Field(default=None, max_length=30)
    notes: str | None = Field(default=None, max_length=1000)


class ReservationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    restaurant_id: int
    table_id: int
    table_number: str | None = None
    table_capacity: int | None = None
    user_id: int | None
    order_id: int | None
    party_size: int
    starts_at: datetime
    ends_at: datetime
    status: ReservationStatus
    hold_expires_at: datetime | None
    guest_name: str
    guest_email: str | None
    guest_phone: str | None
    notes: str | None
    created_at: datetime
    # Seated guests still at the table past their booked end time (0 = not overdue).
    overdue_minutes: int = 0
    # For an upcoming booking: name of the seated party still occupying its table when it is due.
    blocked_by: str | None = None
    # The guest tapped "I'll be there" from the reminder email.
    guest_confirmed_at: datetime | None = None


class AvailableTableRead(BaseModel):
    id: int
    table_number: str
    capacity: int
    zone: str | None = None
    status: str


class ReservationConflict(BaseModel):
    """An existing booking that overlaps the requested slot."""

    id: int
    guest_name: str
    party_size: int
    starts_at: datetime
    ends_at: datetime
    status: ReservationStatus


class TableReservationBrief(BaseModel):
    id: int
    guest_name: str
    guest_phone: str | None = None
    party_size: int
    starts_at: datetime
    ends_at: datetime
    status: ReservationStatus
    # True when this booking is what makes the table RESERVED/OCCUPIED right now.
    blocking: bool = False
    overdue_minutes: int = 0


class AdminTableAvailability(BaseModel):
    id: int
    table_number: str
    capacity: int
    zone: str | None = None
    shape: str = "SQUARE"
    pos_x: float | None = None
    pos_y: float | None = None
    floor_status: str
    # AVAILABLE | RESERVED | OCCUPIED | CLEANING | TOO_SMALL — for the requested slot, not "now".
    slot_status: str
    available: bool
    conflicts: list[ReservationConflict] = Field(default_factory=list)


class FloorTableRead(BaseModel):
    """A table on the customer-facing floor plan, with its state for the searched slot."""

    id: int
    table_number: str
    capacity: int
    zone: str | None = None
    shape: str = "SQUARE"
    pos_x: float | None = None
    pos_y: float | None = None
    # AVAILABLE | UNAVAILABLE (taken at that time) | TOO_SMALL (for the party)
    state: str


class AvailabilityResponse(BaseModel):
    starts_at: datetime
    ends_at: datetime
    party_size: int
    tables: list[AvailableTableRead]
    # Every active table with its state, so the client can draw the seating plan.
    floor: list[FloorTableRead] = Field(default_factory=list)
    # Nearby start times that do have a free table (only filled when `tables` is empty).
    suggested_times: list[datetime] = Field(default_factory=list)


class AdminAvailabilityResponse(BaseModel):
    starts_at: datetime
    ends_at: datetime
    party_size: int
    tables: list[AdminTableAvailability]
