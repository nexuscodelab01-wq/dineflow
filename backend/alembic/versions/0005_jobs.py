"""Add the background jobs table

Revision ID: 0005_jobs
Revises: 0004_table_floor_plan
Create Date: 2026-09-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0005_jobs"
down_revision: Union[str, None] = "0004_table_floor_plan"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("type", sa.String(length=100), nullable=False),
        sa.Column("payload", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        # queued -> running -> succeeded | (queued again after a failure) | dead (out of attempts)
        sa.Column("status", sa.String(length=20), server_default="queued", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="5", nullable=False),
        sa.Column("run_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_by", sa.String(length=100), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        # Which tenant the work is for (NULL = platform-level work).
        sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=True),
        # Optional idempotency key: only one queued/running job may hold a given key.
        sa.Column("dedupe_key", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_jobs_due", "jobs", ["status", "run_at"])
    op.create_index("ix_jobs_restaurant_id", "jobs", ["restaurant_id"])
    op.create_index(
        "uq_jobs_dedupe_active", "jobs", ["dedupe_key"], unique=True,
        postgresql_where=sa.text("dedupe_key IS NOT NULL AND status IN ('queued', 'running')"),
    )


def downgrade() -> None:
    op.drop_index("uq_jobs_dedupe_active", table_name="jobs")
    op.drop_index("ix_jobs_restaurant_id", table_name="jobs")
    op.drop_index("ix_jobs_due", table_name="jobs")
    op.drop_table("jobs")
