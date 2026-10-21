"""A paired POS device (an iPad at a till) — identity for a machine, not a person.

Not modeled on RefreshToken: a refresh token is an *opaque* bearer value looked up by its hash and
exchanged for a JWT, which matters when the value crosses the network often (storing only a hash limits
what a DB leak exposes). A device token is a self-contained signed JWT instead — the same shape as
every other token in this codebase (access, guest, reservation_action): the JWT's signature *is* the
security, and this row's `revoked_at` is the live revocation check (re-checked on every request, the
same way RestaurantUser.is_active is, never cached) — see app/core/security.py's create_device_token
and app/dependencies/pos.py. No expires_at: pairing is meant to last indefinitely until revoked.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.restaurant import Restaurant
    from app.models.user import User


TILL = "TILL"  # a fixed register: mandatory shift + starting float, Z-report at close
HANDHELD = "HANDHELD"  # carried by a server: no drawer, so no float gate (cash is attributed per person)


class Device(TimestampMixin, Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    # What the device is *for*, not its form factor: whether it owns a cash drawer. Existing devices are tills.
    kind: Mapped[str] = mapped_column(String(10), default=TILL, server_default=TILL, nullable=False)
    paired_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # A network receipt printer (ESC/POS over TCP, usually port 9100) this till prints to, and whether it kicks the
    # cash drawer wired to it. With no host the till falls back to AirPrint / the share sheet.
    printer_host: Mapped[str | None] = mapped_column(String(100), nullable=True)
    printer_port: Mapped[int] = mapped_column(Integer, default=9100, server_default="9100", nullable=False)
    cash_drawer: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    auto_print: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)

    restaurant: Mapped["Restaurant"] = relationship("Restaurant")
    paired_by: Mapped["User | None"] = relationship("User", foreign_keys=[paired_by_user_id])
    revoked_by: Mapped["User | None"] = relationship("User", foreign_keys=[revoked_by_user_id])
