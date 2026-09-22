"""Restaurant timezone and closures

Revision ID: 0014_opening_hours
Revises: 0013_row_level_security
Create Date: 2026-09-28

Expand step only: two new columns, both with defaults, so existing restaurants keep working exactly as
before (UTC, no extra closed days) until an admin sets real values.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0014_opening_hours"
down_revision: Union[str, None] = "0013_row_level_security"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("restaurants", sa.Column("timezone", sa.String(64), server_default="UTC", nullable=False))
    op.add_column("restaurants", sa.Column("closures", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False))


def downgrade() -> None:
    op.drop_column("restaurants", "closures")
    op.drop_column("restaurants", "timezone")
