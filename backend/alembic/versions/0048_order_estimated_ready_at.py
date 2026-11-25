"""When staff expect an order to be ready

Revision ID: 0048_order_estimated_ready_at
Revises: 0047_menu_labels
Create Date: 2026-11-25

Adds a nullable `orders.estimated_ready_at`: the time the kitchen tells the customer their pickup or
delivery will be ready ("about 1 h 30"). Staff set and change it; it is empty until they do, so this
needs no backfill and existing orders are untouched.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0048_order_estimated_ready_at"
down_revision: Union[str, None] = "0047_menu_labels"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("estimated_ready_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("orders", "estimated_ready_at")
