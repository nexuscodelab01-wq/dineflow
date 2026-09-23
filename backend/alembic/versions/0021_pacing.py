"""Booking pacing: max covers per 15-minute slot

Revision ID: 0021_pacing
Revises: 0020_waitlist
Create Date: 2026-09-24

Expand step only: one nullable column. Null (the default) reproduces today's behaviour — no cap.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0021_pacing"
down_revision: Union[str, None] = "0020_waitlist"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("restaurants", sa.Column("max_covers_per_slot", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("restaurants", "max_covers_per_slot")
