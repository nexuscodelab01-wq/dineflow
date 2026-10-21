"""Table-less bar tabs (ephemeral tables)

Revision ID: 0045_bar_tabs
Revises: 0044_receipts_printing
Create Date: 2026-10-21
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0045_bar_tabs"
down_revision: Union[str, None] = "0044_receipts_printing"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("restaurant_tables", sa.Column("ephemeral", sa.Boolean(), server_default="false", nullable=False))


def downgrade() -> None:
    op.drop_column("restaurant_tables", "ephemeral")
