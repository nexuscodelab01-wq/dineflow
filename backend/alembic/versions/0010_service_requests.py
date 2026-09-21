"""Service requests: call the waiter, ask for the bill

Revision ID: 0010_service_requests
Revises: 0009_table_sessions
Create Date: 2026-09-24

Expand step only: one new table.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0010_service_requests"
down_revision: Union[str, None] = "0009_table_sessions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "service_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("table_session_id", sa.Integer(), sa.ForeignKey("table_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("table_id", sa.Integer(), sa.ForeignKey("restaurant_tables.id", ondelete="CASCADE"), nullable=False),
        sa.Column("guest_id", sa.Integer(), sa.ForeignKey("session_guests.id", ondelete="SET NULL"), nullable=True),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("state", sa.String(10), server_default="OPEN", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_service_requests_restaurant_id", "service_requests", ["restaurant_id"])
    op.create_index("ix_service_requests_table_session_id", "service_requests", ["table_session_id"])
    op.create_index(
        "uq_service_requests_one_open", "service_requests", ["table_session_id", "kind"], unique=True,
        postgresql_where=sa.text("state = 'OPEN'"),
    )


def downgrade() -> None:
    op.drop_index("uq_service_requests_one_open", table_name="service_requests")
    op.drop_index("ix_service_requests_table_session_id", table_name="service_requests")
    op.drop_index("ix_service_requests_restaurant_id", table_name="service_requests")
    op.drop_table("service_requests")
