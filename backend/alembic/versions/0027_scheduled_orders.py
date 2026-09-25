"""Scheduled collection slots and ordering capacity controls

Revision ID: 0027_scheduled_orders
Revises: 0026_coupons
Create Date: 2026-09-25

Expand only: scalar columns with defaults, so old code keeps working while this rolls out. No new
tables, so no row-level security policy is needed — `orders` and `restaurants` already have theirs.

Defaults are deliberately the current behaviour: ordering is not paused, there is no pending cap and
no per-slot cap, so nothing changes for an existing restaurant until someone sets it.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0027_scheduled_orders"
down_revision: Union[str, None] = "0026_coupons"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("restaurants", sa.Column("online_ordering_paused", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("restaurants", sa.Column("ordering_pause_reason", sa.String(length=200), nullable=True))
    op.add_column("restaurants", sa.Column("max_pending_orders", sa.Integer(), nullable=True))
    op.add_column("restaurants", sa.Column("slot_interval_minutes", sa.Integer(), server_default="15", nullable=False))
    op.add_column("restaurants", sa.Column("max_orders_per_slot", sa.Integer(), nullable=True))
    op.add_column("restaurants", sa.Column("scheduled_order_days_ahead", sa.Integer(), server_default="7", nullable=False))
    op.add_column("restaurants", sa.Column("scheduled_order_lead_minutes", sa.Integer(), server_default="30", nullable=False))

    op.add_column("orders", sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f("ix_orders_scheduled_for"), "orders", ["scheduled_for"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_orders_scheduled_for"), table_name="orders")
    op.drop_column("orders", "scheduled_for")

    for column in (
        "scheduled_order_lead_minutes",
        "scheduled_order_days_ahead",
        "max_orders_per_slot",
        "slot_interval_minutes",
        "max_pending_orders",
        "ordering_pause_reason",
        "online_ordering_paused",
    ):
        op.drop_column("restaurants", column)
