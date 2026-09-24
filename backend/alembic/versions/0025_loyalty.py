"""Loyalty points

Revision ID: 0025_loyalty
Revises: 0024_reviews
Create Date: 2026-09-24

New tenant tables, so each needs a row-level security policy of its own (same shape as reviews' in
0024_reviews) — otherwise tests/test_row_level_security.py::test_every_tenant_table_has_a_policy fails.
Plus one expand-only column on restaurants for the earn rate.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0025_loyalty"
down_revision: Union[str, None] = "0024_reviews"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

REASONS = ["EARNED", "REDEEMED", "ADJUSTED"]


def upgrade() -> None:
    op.add_column(
        "restaurants",
        sa.Column("loyalty_points_per_currency", sa.Integer(), server_default="1", nullable=False),
    )

    bind = op.get_bind()
    postgresql.ENUM(*REASONS, name="loyalty_reason").create(bind, checkfirst=True)

    op.create_table(
        "loyalty_accounts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("restaurant_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("balance", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["restaurant_id"], ["restaurants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("restaurant_id", "user_id", name="uq_loyalty_accounts_user"),
    )
    op.create_index(op.f("ix_loyalty_accounts_restaurant_id"), "loyalty_accounts", ["restaurant_id"], unique=False)
    op.create_index(op.f("ix_loyalty_accounts_user_id"), "loyalty_accounts", ["user_id"], unique=False)
    op.execute("ALTER TABLE loyalty_accounts ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON loyalty_accounts "
        "USING (app_rls_off() OR restaurant_id = app_rls_tenant()) "
        "WITH CHECK (app_rls_off() OR restaurant_id = app_rls_tenant())"
    )

    op.create_table(
        "loyalty_transactions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("restaurant_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=True),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("reason", postgresql.ENUM(*REASONS, name="loyalty_reason", create_type=False), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["restaurant_id"], ["restaurants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_id", name="uq_loyalty_transactions_order"),
    )
    op.create_index(op.f("ix_loyalty_transactions_restaurant_id"), "loyalty_transactions", ["restaurant_id"], unique=False)
    op.create_index(op.f("ix_loyalty_transactions_user_id"), "loyalty_transactions", ["user_id"], unique=False)
    op.execute("ALTER TABLE loyalty_transactions ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON loyalty_transactions "
        "USING (app_rls_off() OR restaurant_id = app_rls_tenant()) "
        "WITH CHECK (app_rls_off() OR restaurant_id = app_rls_tenant())"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON loyalty_transactions")
    op.drop_index(op.f("ix_loyalty_transactions_user_id"), table_name="loyalty_transactions")
    op.drop_index(op.f("ix_loyalty_transactions_restaurant_id"), table_name="loyalty_transactions")
    op.drop_table("loyalty_transactions")

    op.execute("DROP POLICY IF EXISTS tenant_isolation ON loyalty_accounts")
    op.drop_index(op.f("ix_loyalty_accounts_user_id"), table_name="loyalty_accounts")
    op.drop_index(op.f("ix_loyalty_accounts_restaurant_id"), table_name="loyalty_accounts")
    op.drop_table("loyalty_accounts")

    postgresql.ENUM(name="loyalty_reason").drop(op.get_bind(), checkfirst=True)
    op.drop_column("restaurants", "loyalty_points_per_currency")
