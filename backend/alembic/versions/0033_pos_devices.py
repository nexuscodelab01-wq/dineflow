"""POS: paired devices, staff PINs, a COUNTER order type

Revision ID: 0033_pos_devices
Revises: 0032_feature_catalog
Create Date: 2026-10-13

New tenant table `devices` (an iPad paired to one restaurant, revocable — see app/models/device.py),
RLS'd the same way every per-tenant table is (0025_loyalty.py is the exact template). A nullable
`pin_hash` on `restaurant_users` (POS quick-switch PIN, scoped per membership, not per account — same
person can hold a different PIN at a different restaurant). And a new `COUNTER` value on the existing
`order_type` enum, for orders rung in at a POS till (no table, nothing to deliver).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0033_pos_devices"
down_revision: Union[str, None] = "0032_feature_catalog"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "devices",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("restaurant_id", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.Column("paired_by_user_id", sa.Integer(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by_user_id", sa.Integer(), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["restaurant_id"], ["restaurants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["paired_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["revoked_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_devices_restaurant_id"), "devices", ["restaurant_id"], unique=False)
    op.execute("ALTER TABLE devices ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON devices "
        "USING (app_rls_off() OR restaurant_id = app_rls_tenant()) "
        "WITH CHECK (app_rls_off() OR restaurant_id = app_rls_tenant())"
    )

    op.add_column("restaurant_users", sa.Column("pin_hash", sa.String(length=255), nullable=True))

    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE order_type ADD VALUE IF NOT EXISTS 'COUNTER'")


def downgrade() -> None:
    op.drop_column("restaurant_users", "pin_hash")

    op.execute("DROP POLICY IF EXISTS tenant_isolation ON devices")
    op.drop_index(op.f("ix_devices_restaurant_id"), table_name="devices")
    op.drop_table("devices")

    # Postgres can't drop a single enum value; downgrading 'order_type' back to its pre-COUNTER shape
    # would need recreating the type, which is out of scope for a routine rollback.
