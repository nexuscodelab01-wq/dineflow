"""Feature flag overrides and an audit log

Revision ID: 0007_feature_flags
Revises: 0006_tenant_scoping
Create Date: 2026-09-22

Flags are declared in code (app/core/features.py); this table only stores a restaurant's deviation from
a flag's default. The audit log records who changed what, for flags now and other sensitive actions later.
Expand step only: two new tables.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0007_feature_flags"
down_revision: Union[str, None] = "0006_tenant_scoping"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "feature_overrides",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("restaurant_id", "key", name="uq_feature_overrides_restaurant_key"),
    )
    op.create_index("ix_feature_overrides_restaurant_id", "feature_overrides", ["restaurant_id"])

    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurants.id", ondelete="SET NULL"), nullable=True),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("actor_label", sa.String(255), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("target", sa.String(200), nullable=True),
        sa.Column("details", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_audit_log_restaurant_created", "audit_log", ["restaurant_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_log_restaurant_created", table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_index("ix_feature_overrides_restaurant_id", table_name="feature_overrides")
    op.drop_table("feature_overrides")
