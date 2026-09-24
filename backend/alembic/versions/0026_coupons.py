"""Discount coupons

Revision ID: 0026_coupons
Revises: 0025_loyalty
Create Date: 2026-09-24

Two new tenant tables, so each needs a row-level security policy of its own (same shape as
loyalty's in 0025_loyalty) — otherwise tests/test_row_level_security.py::test_every_tenant_table_has_a_policy
fails. Nothing on `orders` changes: the discount column it already has is what a coupon sets.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0026_coupons"
down_revision: Union[str, None] = "0025_loyalty"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DISCOUNT_TYPES = ["PERCENT", "FIXED"]


def upgrade() -> None:
    postgresql.ENUM(*DISCOUNT_TYPES, name="coupon_discount_type").create(op.get_bind(), checkfirst=True)

    op.create_table(
        "coupons",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("restaurant_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("description", sa.String(length=200), nullable=True),
        sa.Column("discount_type", postgresql.ENUM(*DISCOUNT_TYPES, name="coupon_discount_type", create_type=False), nullable=False),
        sa.Column("discount_value", sa.Numeric(10, 2), nullable=False),
        sa.Column("min_order_amount", sa.Numeric(10, 2), nullable=True),
        sa.Column("max_discount_amount", sa.Numeric(10, 2), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("max_redemptions", sa.Integer(), nullable=True),
        sa.Column("max_per_customer", sa.Integer(), nullable=True),
        sa.Column("times_redeemed", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["restaurant_id"], ["restaurants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("restaurant_id", "code", name="uq_coupons_restaurant_code"),
    )
    op.create_index(op.f("ix_coupons_restaurant_id"), "coupons", ["restaurant_id"], unique=False)
    op.create_index(op.f("ix_coupons_code"), "coupons", ["code"], unique=False)
    op.execute("ALTER TABLE coupons ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON coupons "
        "USING (app_rls_off() OR restaurant_id = app_rls_tenant()) "
        "WITH CHECK (app_rls_off() OR restaurant_id = app_rls_tenant())"
    )

    op.create_table(
        "coupon_redemptions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("restaurant_id", sa.Integer(), nullable=False),
        sa.Column("coupon_id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["restaurant_id"], ["restaurants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["coupon_id"], ["coupons.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_id", name="uq_coupon_redemptions_order"),
    )
    op.create_index(op.f("ix_coupon_redemptions_restaurant_id"), "coupon_redemptions", ["restaurant_id"], unique=False)
    op.create_index(op.f("ix_coupon_redemptions_coupon_id"), "coupon_redemptions", ["coupon_id"], unique=False)
    op.create_index(op.f("ix_coupon_redemptions_user_id"), "coupon_redemptions", ["user_id"], unique=False)
    op.execute("ALTER TABLE coupon_redemptions ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON coupon_redemptions "
        "USING (app_rls_off() OR restaurant_id = app_rls_tenant()) "
        "WITH CHECK (app_rls_off() OR restaurant_id = app_rls_tenant())"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON coupon_redemptions")
    op.drop_index(op.f("ix_coupon_redemptions_user_id"), table_name="coupon_redemptions")
    op.drop_index(op.f("ix_coupon_redemptions_coupon_id"), table_name="coupon_redemptions")
    op.drop_index(op.f("ix_coupon_redemptions_restaurant_id"), table_name="coupon_redemptions")
    op.drop_table("coupon_redemptions")

    op.execute("DROP POLICY IF EXISTS tenant_isolation ON coupons")
    op.drop_index(op.f("ix_coupons_code"), table_name="coupons")
    op.drop_index(op.f("ix_coupons_restaurant_id"), table_name="coupons")
    op.drop_table("coupons")

    postgresql.ENUM(name="coupon_discount_type").drop(op.get_bind(), checkfirst=True)
