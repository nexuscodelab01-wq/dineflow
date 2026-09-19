"""Add per-restaurant reservation turnover buffer

Revision ID: 0003_reservation_buffer
Revises: 0002_reservations
Create Date: 2026-09-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003_reservation_buffer"
down_revision: Union[str, None] = "0002_reservations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Minutes a table is held free after a booking ends (clearing, resetting, and slack for
    # parties that run slightly over). Existing restaurants get a 15-minute default.
    op.add_column(
        "restaurants",
        sa.Column("reservation_buffer_minutes", sa.Integer(), server_default="15", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("restaurants", "reservation_buffer_minutes")
