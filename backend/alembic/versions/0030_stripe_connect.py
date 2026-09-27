"""Stripe Connect: restaurant accounts and a real payment shape

Revision ID: 0030_stripe_connect
Revises: 0029_menu_item_allergens
Create Date: 2026-09-26

Expand-only, no backfill needed (every new/existing column has a default): foundation for Sprint 4
Phase 1 (see the plan for the full design). `payments` gains what it needs to describe a real
transaction; `restaurants` gains what Stripe Connect onboarding needs. Refunds (`refunded_amount`) and
tips land with their own phases, not here.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0030_stripe_connect"
down_revision: Union[str, None] = "0029_menu_item_allergens"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("restaurants", sa.Column("currency", sa.String(length=3), server_default="usd", nullable=False))
    op.add_column("restaurants", sa.Column("stripe_account_id", sa.String(length=255), nullable=True))
    op.add_column("restaurants", sa.Column("stripe_charges_enabled", sa.Boolean(), server_default="false", nullable=False))

    op.add_column("payments", sa.Column("restaurant_id", sa.Integer(), nullable=True))
    op.execute("UPDATE payments AS p SET restaurant_id = o.restaurant_id FROM orders AS o WHERE o.id = p.order_id")
    op.alter_column("payments", "restaurant_id", nullable=False)
    op.create_index("ix_payments_restaurant_id", "payments", ["restaurant_id"])
    op.create_foreign_key(
        "fk_payments_restaurant_id", "payments", "restaurants", ["restaurant_id"], ["id"], ondelete="CASCADE"
    )

    op.add_column("payments", sa.Column("currency", sa.String(length=3), server_default="usd", nullable=False))
    op.add_column("payments", sa.Column("provider", sa.String(length=20), server_default="MOCK", nullable=False))
    op.add_column("payments", sa.Column("provider_intent_id", sa.String(length=255), nullable=True))
    op.create_index("ix_payments_provider_intent_id", "payments", ["provider_intent_id"])
    op.add_column(
        "payments",
        sa.Column("application_fee_amount", sa.Numeric(10, 2), server_default="0.00", nullable=False),
    )
    op.add_column("payments", sa.Column("failure_message", sa.String(length=500), nullable=True))

    # New enum members. Postgres requires ALTER TYPE ... ADD VALUE outside a transaction block.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE payment_status ADD VALUE IF NOT EXISTS 'REQUIRES_ACTION'")
        op.execute("ALTER TYPE payment_method ADD VALUE IF NOT EXISTS 'CARD'")


def downgrade() -> None:
    # Enum values can't be dropped in Postgres without recreating the type; left in place on downgrade
    # (harmless — nothing writes them once the app code is rolled back).
    op.drop_column("payments", "failure_message")
    op.drop_column("payments", "application_fee_amount")
    op.drop_index("ix_payments_provider_intent_id", table_name="payments")
    op.drop_column("payments", "provider_intent_id")
    op.drop_column("payments", "provider")
    op.drop_column("payments", "currency")
    op.drop_constraint("fk_payments_restaurant_id", "payments", type_="foreignkey")
    op.drop_index("ix_payments_restaurant_id", table_name="payments")
    op.drop_column("payments", "restaurant_id")
    op.drop_column("restaurants", "stripe_charges_enabled")
    op.drop_column("restaurants", "stripe_account_id")
    op.drop_column("restaurants", "currency")
