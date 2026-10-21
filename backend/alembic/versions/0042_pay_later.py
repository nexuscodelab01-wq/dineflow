"""Pay at pickup / cash on delivery

Revision ID: 0042_pay_later
Revises: 0041_pos_controls
Create Date: 2026-10-21

Off by default for every restaurant, and existing orders are not pay-later.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0042_pay_later"
down_revision: Union[str, None] = "0041_pos_controls"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("restaurants", sa.Column("pay_at_pickup_enabled", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("restaurants", sa.Column("cash_on_delivery_enabled", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("restaurants", sa.Column("pay_later_max_order", sa.Numeric(10, 2), server_default="100.00", nullable=False))
    op.add_column("restaurants", sa.Column("pay_later_first_order_prepaid", sa.Boolean(), server_default="true", nullable=False))
    op.add_column("orders", sa.Column("pay_later", sa.Boolean(), server_default="false", nullable=False))


def downgrade() -> None:
    op.drop_column("orders", "pay_later")
    for col in ("pay_later_first_order_prepaid", "pay_later_max_order", "cash_on_delivery_enabled", "pay_at_pickup_enabled"):
        op.drop_column("restaurants", col)
