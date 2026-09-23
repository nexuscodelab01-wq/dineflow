"""Walk-in waitlist

Revision ID: 0020_waitlist
Revises: 0019_booking_policy
Create Date: 2026-09-23

New tenant table, so it needs a row-level security policy of its own (same shape as reservations'
in 0013_row_level_security) — otherwise tests/test_row_level_security.py::test_every_tenant_table_has_a_policy
fails.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0020_waitlist"
down_revision: Union[str, None] = "0019_booking_policy"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

STATUSES = ["WAITING", "NOTIFIED", "SEATED", "CANCELLED"]


def upgrade() -> None:
    bind = op.get_bind()
    postgresql.ENUM(*STATUSES, name="waitlist_status").create(bind, checkfirst=True)

    op.create_table(
        "waitlist_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("restaurant_id", sa.Integer(), nullable=False),
        sa.Column("guest_name", sa.String(length=200), nullable=False),
        sa.Column("guest_email", sa.String(length=255), nullable=True),
        sa.Column("guest_phone", sa.String(length=30), nullable=True),
        sa.Column("party_size", sa.Integer(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("quoted_minutes", sa.Integer(), nullable=True),
        sa.Column("status", postgresql.ENUM(*STATUSES, name="waitlist_status", create_type=False), nullable=False),
        sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reservation_id", sa.Integer(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["restaurant_id"], ["restaurants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reservation_id"], ["reservations.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_waitlist_entries_restaurant_id"), "waitlist_entries", ["restaurant_id"], unique=False)
    op.create_index(op.f("ix_waitlist_entries_status"), "waitlist_entries", ["status"], unique=False)

    op.execute("ALTER TABLE waitlist_entries ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON waitlist_entries "
        "USING (app_rls_off() OR restaurant_id = app_rls_tenant()) "
        "WITH CHECK (app_rls_off() OR restaurant_id = app_rls_tenant())"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON waitlist_entries")
    op.drop_index(op.f("ix_waitlist_entries_status"), table_name="waitlist_entries")
    op.drop_index(op.f("ix_waitlist_entries_restaurant_id"), table_name="waitlist_entries")
    op.drop_table("waitlist_entries")
    postgresql.ENUM(name="waitlist_status").drop(op.get_bind(), checkfirst=True)
