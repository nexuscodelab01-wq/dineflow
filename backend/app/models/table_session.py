"""A table's shared tab: everyone who scans the table's QR code joins the same open session."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.restaurant_table import RestaurantTable

OPEN = "OPEN"
CLOSED = "CLOSED"


class TableSession(Base):
    __tablename__ = "table_sessions"
    __table_args__ = (
        # A table has at most one open session at any time; joining twice must reach the same one.
        Index("uq_table_sessions_one_open", "table_id", unique=True, postgresql_where=text("state = 'OPEN'")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True)
    table_id: Mapped[int] = mapped_column(ForeignKey("restaurant_tables.id", ondelete="CASCADE"), nullable=False, index=True)
    state: Mapped[str] = mapped_column(String(10), default=OPEN, server_default=OPEN, nullable=False)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    table: Mapped["RestaurantTable"] = relationship("RestaurantTable")


class SessionGuest(Base):
    """One device at the table. Its id goes into that device's token; it can be named ("Sam") or anonymous."""

    __tablename__ = "session_guests"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("table_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
