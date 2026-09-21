"""Single-use links for setting or resetting a password. Only a hash of the token is stored."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

RESET = "RESET"
INVITE = "INVITE"


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"
    __table_args__ = (Index("ix_password_reset_tokens_user_created", "user_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    # The site the link was requested from: its name and address brand the emails and the link.
    restaurant_id: Mapped[int | None] = mapped_column(ForeignKey("restaurants.id", ondelete="SET NULL"), nullable=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    purpose: Mapped[str] = mapped_column(String(10), default=RESET, server_default=RESET, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
