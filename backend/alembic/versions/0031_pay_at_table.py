"""Pay at table: a payment can cover a whole session's tab, not just one order

Revision ID: 0031_pay_at_table
Revises: 0030_stripe_connect
Create Date: 2026-09-27

Expand-only. `payments.order_id` becomes nullable and `payments.table_session_id` is added (nullable FK
to table_sessions) — a table-session payment covers every round on the tab at once, so it isn't tied to
one order. Exactly one of the two is set per row, enforced in TableSessionService/OrderService, not here.
PaymentMethod gains 'CASH' for the pay-at-counter path.

**Also fixes a real RLS bug this change would otherwise hit**: `payments`' row-level-security policy
(migration 0013) is a "child of orders" policy — `EXISTS (SELECT 1 FROM orders WHERE id = payments.order_id)`
— not based on `payments.restaurant_id` (which exists but was never wired into the policy). A
table-session payment has `order_id IS NULL`, so that EXISTS is always false: the row would be invisible
under the restricted role, and WITH CHECK would refuse to let it be inserted at all. Since
`payments.restaurant_id` is set reliably on every row (both kinds), switch the policy to use it directly
— simpler than the join, and correct for both payment kinds.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0031_pay_at_table"
down_revision: Union[str, None] = "0030_stripe_connect"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("payments", "order_id", nullable=True)
    op.add_column("payments", sa.Column("table_session_id", sa.Integer(), nullable=True))
    op.create_index("ix_payments_table_session_id", "payments", ["table_session_id"])
    op.create_foreign_key(
        "fk_payments_table_session_id", "payments", "table_sessions", ["table_session_id"], ["id"], ondelete="CASCADE"
    )
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE payment_method ADD VALUE IF NOT EXISTS 'CASH'")

    op.execute("DROP POLICY IF EXISTS tenant_isolation ON payments")
    op.execute(
        "CREATE POLICY tenant_isolation ON payments "
        "USING (app_rls_off() OR restaurant_id = app_rls_tenant()) "
        "WITH CHECK (app_rls_off() OR restaurant_id = app_rls_tenant())"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON payments")
    op.execute(
        "CREATE POLICY tenant_isolation ON payments "
        "USING (app_rls_off() OR EXISTS (SELECT 1 FROM orders p WHERE p.id = payments.order_id)) "
        "WITH CHECK (app_rls_off() OR EXISTS (SELECT 1 FROM orders p WHERE p.id = payments.order_id))"
    )
    op.drop_constraint("fk_payments_table_session_id", "payments", type_="foreignkey")
    op.drop_index("ix_payments_table_session_id", table_name="payments")
    op.drop_column("payments", "table_session_id")
    op.alter_column("payments", "order_id", nullable=False)
