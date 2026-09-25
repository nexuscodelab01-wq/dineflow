"""Staff membership roles and activation

Revision ID: 0028_staff_membership_roles
Revises: 0027_scheduled_orders
Create Date: 2026-09-25

Expand-backfill-enforce on `restaurant_users`, done in one migration since there is no real client
data yet (safe now; would need splitting into separate expand/backfill/enforce deploys once there is):
- `role`: a per-membership copy of the account's role at the time of this migration (or invite time,
  going forward) — separate from the global `users.role_id`. See restaurant_user.py's docstring for why.
- `is_active`: lets a restaurant remove someone's access without touching their login account, which
  might still be valid elsewhere. Defaults true, so every existing membership keeps working.
- `created_at`/`updated_at` (TimestampMixin): existing memberships backfilled to now(), since we don't
  know when they were actually created.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0028_staff_membership_roles"
down_revision: Union[str, None] = "0027_scheduled_orders"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("restaurant_users", sa.Column("role", sa.String(length=50), nullable=True))
    op.add_column("restaurant_users", sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False))
    op.add_column("restaurant_users", sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False))
    op.add_column("restaurant_users", sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False))

    # Backfill from each member's current global role. Every existing restaurant_users row belongs to
    # a RESTAURANT_ADMIN or RESTAURANT_STAFF user (nothing else ever gets a membership), so this can't
    # leave a row without a role.
    op.execute(
        "UPDATE restaurant_users AS ru SET role = r.name "
        "FROM users u JOIN roles r ON r.id = u.role_id "
        "WHERE u.id = ru.user_id"
    )
    op.alter_column("restaurant_users", "role", nullable=False)


def downgrade() -> None:
    op.drop_column("restaurant_users", "updated_at")
    op.drop_column("restaurant_users", "created_at")
    op.drop_column("restaurant_users", "is_active")
    op.drop_column("restaurant_users", "role")
