"""POS controls: order adjustments (void/comp/discount/refund), line discount, staff permissions

Revision ID: 0041_pos_controls
Revises: 0040_tips_service_charge
Create Date: 2026-10-21
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0041_pos_controls"
down_revision: Union[str, None] = "0040_tips_service_charge"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("order_items", sa.Column("discount_amount", sa.Numeric(10, 2), server_default="0.00", nullable=False))
    op.add_column(
        "restaurants",
        sa.Column(
            "pos_staff_permissions", postgresql.JSONB(),
            server_default=sa.text("""'{"void": false, "comp": false, "refund": false, "discount_max_pct": 10}'::jsonb"""), nullable=False,
        ),
    )
    op.create_table(
        "order_adjustments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("restaurant_id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=True),
        sa.Column("table_session_id", sa.Integer(), nullable=True),
        sa.Column("order_item_id", sa.Integer(), nullable=True),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("reason_code", sa.String(length=30), nullable=False),
        sa.Column("note", sa.String(length=300), nullable=True),
        sa.Column("staff_user_id", sa.Integer(), nullable=True),
        sa.Column("authorized_by_user_id", sa.Integer(), nullable=True),
        sa.Column("shift_id", sa.Integer(), nullable=True),
        sa.Column("payment_method", sa.String(length=10), nullable=True),
        sa.Column("original_shift_id", sa.Integer(), nullable=True),
        sa.Column("detail", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["restaurant_id"], ["restaurants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["table_session_id"], ["table_sessions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["order_item_id"], ["order_items.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["staff_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["authorized_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["shift_id"], ["shifts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    for col in ("restaurant_id", "order_id", "table_session_id", "staff_user_id", "shift_id"):
        op.create_index(op.f(f"ix_order_adjustments_{col}"), "order_adjustments", [col], unique=False)
    op.execute("ALTER TABLE order_adjustments ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON order_adjustments "
        "USING (app_rls_off() OR restaurant_id = app_rls_tenant()) "
        "WITH CHECK (app_rls_off() OR restaurant_id = app_rls_tenant())"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON order_adjustments")
    for col in ("shift_id", "staff_user_id", "table_session_id", "order_id", "restaurant_id"):
        op.drop_index(op.f(f"ix_order_adjustments_{col}"), table_name="order_adjustments")
    op.drop_table("order_adjustments")
    op.drop_column("restaurants", "pos_staff_permissions")
    op.drop_column("order_items", "discount_amount")
