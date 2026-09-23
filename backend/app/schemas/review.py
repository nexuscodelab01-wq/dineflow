"""Review Pydantic schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ReviewCreate(BaseModel):
    """Exactly one of `order_id`/`reservation_id` names the completed visit being reviewed."""

    order_id: int | None = None
    reservation_id: int | None = None
    rating: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _one_visit(self) -> "ReviewCreate":
        if (self.order_id is None) == (self.reservation_id is None):
            raise ValueError("Name exactly one of order_id or reservation_id")
        return self


class ReviewRead(BaseModel):
    """A customer's own view of their review."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: int | None
    reservation_id: int | None
    rating: int
    comment: str | None
    is_published: bool
    staff_reply: str | None
    staff_reply_at: datetime | None
    created_at: datetime


class EligibleVisit(BaseModel):
    """A completed order or reservation with no review yet — a "leave a review" prompt."""

    order_id: int | None = None
    reservation_id: int | None = None
    label: str  # e.g. "Order #BV-1042" or "Table booking, 12 Sep"
    visited_at: datetime


class PublicReviewRead(BaseModel):
    """What a visitor sees: no contact details, just a first name."""

    id: int
    reviewer_name: str
    rating: int
    comment: str | None
    staff_reply: str | None
    staff_reply_at: datetime | None
    created_at: datetime


class PublicReviewList(BaseModel):
    items: list[PublicReviewRead]
    total: int
    page: int
    page_size: int
    pages: int
    average_rating: float | None
    counts_by_rating: dict[int, int]  # {5: 12, 4: 3, ...}


class AdminReviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    reviewer_name: str
    reviewer_email: str | None
    order_id: int | None
    reservation_id: int | None
    rating: int
    comment: str | None
    is_published: bool
    staff_reply: str | None
    staff_reply_at: datetime | None
    created_at: datetime


class ReviewModerate(BaseModel):
    is_published: bool


class ReviewReply(BaseModel):
    reply: str = Field(min_length=1, max_length=2000)
