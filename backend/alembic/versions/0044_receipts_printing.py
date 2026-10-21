"""Receipt printer settings on a device

Revision ID: 0044_receipts_printing
Revises: 0043_floor_ops
Create Date: 2026-10-21
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0044_receipts_printing"
down_revision: Union[str, None] = "0043_floor_ops"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("devices", sa.Column("printer_host", sa.String(length=100), nullable=True))
    op.add_column("devices", sa.Column("printer_port", sa.Integer(), server_default="9100", nullable=False))
    op.add_column("devices", sa.Column("cash_drawer", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("devices", sa.Column("auto_print", sa.Boolean(), server_default="false", nullable=False))


def downgrade() -> None:
    for col in ("auto_print", "cash_drawer", "printer_port", "printer_host"):
        op.drop_column("devices", col)
