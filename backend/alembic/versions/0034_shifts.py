"""Shifts and cash movements (Z-report)

Revision ID: 0034_shifts
Revises: 0033_pos_devices
Create Date: 2026-10-18

New tenant tables `shifts` (a device's till session — a starting float, cash/card totals and variance
all derived at read time, see app/models/shift.py) and `cash_movements` (a cash-drawer adjustment with
no order behind it — a float top-up, a cash tip paid out, etc, see app/models/cash_movement.py), both
RLS'd the same way every per-tenant table is (0033_pos_devices.py is the exact template). `shifts` gets
a partial unique index so a device has at most one open shift at a time — the same template
`uq_table_sessions_one_open` already uses for table sessions (0009_table_sessions.py). A new nullable
`shift_id` on `payments` attributes a POS-taken payment to the till shift it was rung up during.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0034_shifts"
down_revision: Union[str, None] = "0033_pos_devices"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "shifts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("restaurant_id", sa.Integer(), nullable=False),
        sa.Column("device_id", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=10), server_default="OPEN", nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("opened_by_user_id", sa.Integer(), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_by_user_id", sa.Integer(), nullable=True),
        sa.Column("starting_float", sa.Numeric(10, 2), nullable=False),
        sa.Column("counted_cash", sa.Numeric(10, 2), nullable=True),
        sa.ForeignKeyConstraint(["restaurant_id"], ["restaurants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["opened_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["closed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_shifts_restaurant_id"), "shifts", ["restaurant_id"], unique=False)
    op.create_index(op.f("ix_shifts_device_id"), "shifts", ["device_id"], unique=False)
    op.create_index(
        "uq_shifts_one_open_per_device", "shifts", ["device_id"], unique=True,
        postgresql_where=sa.text("state = 'OPEN'"),
    )
    op.execute("ALTER TABLE shifts ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON shifts "
        "USING (app_rls_off() OR restaurant_id = app_rls_tenant()) "
        "WITH CHECK (app_rls_off() OR restaurant_id = app_rls_tenant())"
    )

    cash_movement_kind = postgresql.ENUM("PAID_IN", "PAID_OUT", name="cash_movement_kind")
    cash_movement_kind.create(op.get_bind())

    op.create_table(
        "cash_movements",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("restaurant_id", sa.Integer(), nullable=False),
        sa.Column("shift_id", sa.Integer(), nullable=False),
        sa.Column("kind", postgresql.ENUM("PAID_IN", "PAID_OUT", name="cash_movement_kind", create_type=False), nullable=False),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("reason", sa.String(length=300), nullable=False),
        sa.Column("staff_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["restaurant_id"], ["restaurants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["shift_id"], ["shifts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["staff_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_cash_movements_restaurant_id"), "cash_movements", ["restaurant_id"], unique=False)
    op.create_index(op.f("ix_cash_movements_shift_id"), "cash_movements", ["shift_id"], unique=False)
    op.execute("ALTER TABLE cash_movements ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON cash_movements "
        "USING (app_rls_off() OR restaurant_id = app_rls_tenant()) "
        "WITH CHECK (app_rls_off() OR restaurant_id = app_rls_tenant())"
    )

    op.add_column("payments", sa.Column("shift_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_payments_shift_id_shifts", "payments", "shifts", ["shift_id"], ["id"], ondelete="SET NULL")
    op.create_index(op.f("ix_payments_shift_id"), "payments", ["shift_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_payments_shift_id"), table_name="payments")
    op.drop_constraint("fk_payments_shift_id_shifts", "payments", type_="foreignkey")
    op.drop_column("payments", "shift_id")

    op.execute("DROP POLICY IF EXISTS tenant_isolation ON cash_movements")
    op.drop_index(op.f("ix_cash_movements_shift_id"), table_name="cash_movements")
    op.drop_index(op.f("ix_cash_movements_restaurant_id"), table_name="cash_movements")
    op.drop_table("cash_movements")
    op.execute("DROP TYPE cash_movement_kind")

    op.execute("DROP POLICY IF EXISTS tenant_isolation ON shifts")
    op.drop_index("uq_shifts_one_open_per_device", table_name="shifts")
    op.drop_index(op.f("ix_shifts_device_id"), table_name="shifts")
    op.drop_index(op.f("ix_shifts_restaurant_id"), table_name="shifts")
    op.drop_table("shifts")
