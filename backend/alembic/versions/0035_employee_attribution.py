"""Employee attribution: Payment.staff_user_id, time_entries (clock in/out)

Revision ID: 0035_employee_attribution
Revises: 0034_shifts
Create Date: 2026-10-20

A nullable `staff_user_id` on `payments` — who took the money, set for every POS-initiated tender (NULL
for a guest's own online payment). And a new tenant table `time_entries` (an employee's clock in/out
record, scoped to the person not a till — see app/models/time_entry.py), RLS'd the same way every
per-tenant table is (0034_shifts.py is the exact template), with a partial unique index so a person has
at most one open entry at a time.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0035_employee_attribution"
down_revision: Union[str, None] = "0034_shifts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("payments", sa.Column("staff_user_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_payments_staff_user_id_users", "payments", "users", ["staff_user_id"], ["id"], ondelete="SET NULL")
    op.create_index(op.f("ix_payments_staff_user_id"), "payments", ["staff_user_id"], unique=False)

    op.create_table(
        "time_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("restaurant_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("clock_in_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("clock_in_device_id", sa.Integer(), nullable=True),
        sa.Column("clock_out_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["restaurant_id"], ["restaurants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["clock_in_device_id"], ["devices.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_time_entries_restaurant_id"), "time_entries", ["restaurant_id"], unique=False)
    op.create_index(op.f("ix_time_entries_user_id"), "time_entries", ["user_id"], unique=False)
    op.create_index(
        "uq_time_entries_one_open_per_user", "time_entries", ["restaurant_id", "user_id"], unique=True,
        postgresql_where=sa.text("clock_out_at IS NULL"),
    )
    op.execute("ALTER TABLE time_entries ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON time_entries "
        "USING (app_rls_off() OR restaurant_id = app_rls_tenant()) "
        "WITH CHECK (app_rls_off() OR restaurant_id = app_rls_tenant())"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON time_entries")
    op.drop_index("uq_time_entries_one_open_per_user", table_name="time_entries")
    op.drop_index(op.f("ix_time_entries_user_id"), table_name="time_entries")
    op.drop_index(op.f("ix_time_entries_restaurant_id"), table_name="time_entries")
    op.drop_table("time_entries")

    op.drop_index(op.f("ix_payments_staff_user_id"), table_name="payments")
    op.drop_constraint("fk_payments_staff_user_id_users", "payments", type_="foreignkey")
    op.drop_column("payments", "staff_user_id")
