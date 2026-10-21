"""Tips, service charge, cash-up and the tip allocation ledger

Revision ID: 0040_tips_service_charge
Revises: 0039_stripe_tax
Create Date: 2026-10-21

Everything defaults to off / zero, so existing restaurants behave exactly as before.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0040_tips_service_charge"
down_revision: Union[str, None] = "0039_stripe_tax"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("restaurants", sa.Column("tips_enabled", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("restaurants", sa.Column("tip_presets", postgresql.JSONB(), server_default=sa.text("'[15,20,25]'::jsonb"), nullable=False))
    op.add_column("restaurants", sa.Column("tip_pool_mode", sa.String(length=12), server_default="KEEP", nullable=False))
    op.add_column("restaurants", sa.Column("service_charge_rate", sa.Numeric(5, 4), server_default="0", nullable=False))
    op.add_column("restaurants", sa.Column("service_charge_order_types", postgresql.JSONB(), server_default=sa.text("""'["DINE_IN"]'::jsonb"""), nullable=False))
    op.add_column("restaurants", sa.Column("service_charge_taxable", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("restaurants", sa.Column("stripe_terminal_location_id", sa.String(length=64), nullable=True))
    op.add_column("restaurants", sa.Column("stripe_terminal_config_id", sa.String(length=64), nullable=True))
    op.add_column("payments", sa.Column("tip_amount", sa.Numeric(10, 2), server_default="0.00", nullable=False))
    op.add_column("orders", sa.Column("service_charge", sa.Numeric(10, 2), server_default="0.00", nullable=False))
    op.add_column("shifts", sa.Column("cash_tips", sa.Numeric(10, 2), server_default="0.00", nullable=False))
    op.add_column("time_entries", sa.Column("counted_cash", sa.Numeric(10, 2), nullable=True))
    op.add_column("time_entries", sa.Column("cash_tips", sa.Numeric(10, 2), server_default="0.00", nullable=False))

    op.create_table(
        "tip_allocations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("restaurant_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("mode", sa.String(length=12), nullable=False),
        sa.Column("collected", sa.Numeric(10, 2), nullable=False),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("hours", sa.Numeric(8, 2), server_default="0.00", nullable=False),
        sa.Column("finalized_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["restaurant_id"], ["restaurants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["finalized_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_tip_allocations_restaurant_id"), "tip_allocations", ["restaurant_id"], unique=False)
    op.create_index(op.f("ix_tip_allocations_user_id"), "tip_allocations", ["user_id"], unique=False)
    op.execute("ALTER TABLE tip_allocations ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON tip_allocations "
        "USING (app_rls_off() OR restaurant_id = app_rls_tenant()) "
        "WITH CHECK (app_rls_off() OR restaurant_id = app_rls_tenant())"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON tip_allocations")
    op.drop_index(op.f("ix_tip_allocations_user_id"), table_name="tip_allocations")
    op.drop_index(op.f("ix_tip_allocations_restaurant_id"), table_name="tip_allocations")
    op.drop_table("tip_allocations")
    op.drop_column("time_entries", "cash_tips")
    op.drop_column("time_entries", "counted_cash")
    op.drop_column("shifts", "cash_tips")
    op.drop_column("orders", "service_charge")
    op.drop_column("payments", "tip_amount")
    for col in ("stripe_terminal_config_id", "stripe_terminal_location_id", "service_charge_taxable", "service_charge_order_types",
                "service_charge_rate", "tip_pool_mode", "tip_presets", "tips_enabled"):
        op.drop_column("restaurants", col)
