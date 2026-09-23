"""Table combining: a reservation can span more than one table

Revision ID: 0022_table_combining
Revises: 0021_pacing
Create Date: 2026-09-24

Expand step only: one JSONB column, same pattern as `closures` on Restaurant — no FK, ids are
validated in the service on every write. Existing reservations get an empty list (single table,
today's behaviour, unchanged).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0022_table_combining"
down_revision: Union[str, None] = "0021_pacing"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "reservations",
        sa.Column("extra_table_ids", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("reservations", "extra_table_ids")
