"""Restaurant staff membership ORM model.

`role` is deliberately separate from the global `User.role_id`: a person's *account* role (are they
staff at all) and their role *at this restaurant* are different questions, and keeping them apart is
what lets the same account be an admin at one restaurant and plain staff at another later, and is a
prerequisite for shared-device PIN switching (kiosk/POS). Only RESTAURANT_ADMIN and RESTAURANT_STAFF
are valid here — a membership row only ever exists for those two roles in the first place.

Authorization still runs on the global role today (`app/dependencies/restaurant.py`), not on this
column directly — a real per-membership authorization check is a later redesign, not this sprint's.
What *does* already happen: `StaffService._sync_global_role` promotes the global role the moment a
membership here grants RESTAURANT_ADMIN, so "make them an admin" isn't a lie the UI tells while every
admin-only route keeps refusing them. It never demotes — row-level security means a tenant-scoped
request can only ever see this one restaurant's rows, so there is no safe way to confirm "not an admin
anywhere else" from inside it. A demotion still takes effect immediately where it matters: their
*access to this restaurant*, gated by `is_active` below, not by the global role.

`is_active` is live immediately in the other sense too: checked on every request via
`user_can_access_restaurant`, so flipping it off revokes a staff member's access to this restaurant on
their very next API call, no token revocation needed.
"""

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import RoleName
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.restaurant import Restaurant
    from app.models.user import User


class RestaurantUser(TimestampMixin, Base):
    __tablename__ = "restaurant_users"
    __table_args__ = (UniqueConstraint("restaurant_id", "user_id", name="uq_restaurant_user"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(
        ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # A plain string, like Role.name — not a native Postgres enum, so this table needs no type
    # migration if RoleName ever grows a finer-grained role (manager, host, kitchen…).
    role: Mapped[RoleName] = mapped_column(String(50), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)

    restaurant: Mapped["Restaurant"] = relationship("Restaurant", back_populates="staff")
    user: Mapped["User"] = relationship("User", back_populates="restaurant_memberships")
