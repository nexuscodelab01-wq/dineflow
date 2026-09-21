"""A guest asking for something from their table: the waiter, or the bill."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

WAITER = "WAITER"
BILL = "BILL"
KINDS = (WAITER, BILL)
OPEN = "OPEN"
DONE = "DONE"


class ServiceRequest(Base):
    __tablename__ = "service_requests"
    __table_args__ = (
        # Tapping "call waiter" five times is one request, not five: a table has at most one open request per kind.
        Index("uq_service_requests_one_open", "table_session_id", "kind", unique=True, postgresql_where=text("state = 'OPEN'")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True)
    table_session_id: Mapped[int] = mapped_column(ForeignKey("table_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    table_id: Mapped[int] = mapped_column(ForeignKey("restaurant_tables.id", ondelete="CASCADE"), nullable=False)
    guest_id: Mapped[int | None] = mapped_column(ForeignKey("session_guests.id", ondelete="SET NULL"), nullable=True)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    state: Mapped[str] = mapped_column(String(10), default=OPEN, server_default=OPEN, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
