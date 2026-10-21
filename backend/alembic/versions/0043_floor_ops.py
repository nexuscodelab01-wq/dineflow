"""Floor ops: course firing, split-payment item tracking, tab names

Revision ID: 0043_floor_ops
Revises: 0042_pay_later
Create Date: 2026-10-21
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0043_floor_ops"
down_revision: Union[str, None] = "0042_pay_later"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("order_items", sa.Column("course", sa.Integer(), server_default="1", nullable=False))
    op.add_column("order_items", sa.Column("held", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("order_items", sa.Column("paid_payment_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_order_items_paid_payment_id_payments", "order_items", "payments", ["paid_payment_id"], ["id"], ondelete="SET NULL")
    op.add_column("table_sessions", sa.Column("tab_name", sa.String(length=60), nullable=True))


def downgrade() -> None:
    op.drop_column("table_sessions", "tab_name")
    op.drop_constraint("fk_order_items_paid_payment_id_payments", "order_items", type_="foreignkey")
    for col in ("paid_payment_id", "held", "course"):
        op.drop_column("order_items", col)
