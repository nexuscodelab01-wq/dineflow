"""Stripe Tax: restaurant state/tax mode/default code, address state, item tax code, order tax calculation

Revision ID: 0039_stripe_tax
Revises: 0038_restaurant_country
Create Date: 2026-10-21

Everything defaults to today's behaviour (FLAT mode, no codes), so existing restaurants are unchanged.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0039_stripe_tax"
down_revision: Union[str, None] = "0038_restaurant_country"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("restaurants", sa.Column("state", sa.String(length=3), nullable=True))
    op.add_column("restaurants", sa.Column("tax_mode", sa.String(length=10), server_default="FLAT", nullable=False))
    op.add_column("restaurants", sa.Column("default_tax_code", sa.String(length=20), server_default="txcd_40060003", nullable=False))
    op.add_column("addresses", sa.Column("state", sa.String(length=3), nullable=True))
    op.add_column("menu_items", sa.Column("tax_code", sa.String(length=20), nullable=True))
    op.add_column("order_items", sa.Column("tax_code", sa.String(length=20), nullable=True))
    op.add_column("order_items", sa.Column("tax_amount", sa.Numeric(10, 2), server_default="0", nullable=False))
    op.add_column("orders", sa.Column("tax_calculation_id", sa.String(length=64), nullable=True))
    op.add_column("orders", sa.Column("tax_transaction_id", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("orders", "tax_transaction_id")
    op.drop_column("orders", "tax_calculation_id")
    op.drop_column("order_items", "tax_amount")
    op.drop_column("order_items", "tax_code")
    op.drop_column("menu_items", "tax_code")
    op.drop_column("addresses", "state")
    op.drop_column("restaurants", "default_tax_code")
    op.drop_column("restaurants", "tax_mode")
    op.drop_column("restaurants", "state")
