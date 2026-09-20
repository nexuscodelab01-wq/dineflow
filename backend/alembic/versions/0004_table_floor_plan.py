"""Add floor-plan fields to restaurant tables

Revision ID: 0004_table_floor_plan
Revises: 0003_reservation_buffer
Create Date: 2026-09-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004_table_floor_plan"
down_revision: Union[str, None] = "0003_reservation_buffer"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # zone: seating area ("Window", "Bar", "Patio"…). shape: ROUND | SQUARE | RECT.
    # pos_x / pos_y: position on the floor plan as a percentage of its width / height
    # (NULL = not placed yet; the UI lays those out automatically).
    # is_active: retired tables are hidden and unbookable, but keep their booking history.
    op.add_column("restaurant_tables", sa.Column("zone", sa.String(length=50), nullable=True))
    op.add_column("restaurant_tables", sa.Column("shape", sa.String(length=10), server_default="SQUARE", nullable=False))
    op.add_column("restaurant_tables", sa.Column("pos_x", sa.Float(), nullable=True))
    op.add_column("restaurant_tables", sa.Column("pos_y", sa.Float(), nullable=True))
    op.add_column("restaurant_tables", sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False))


def downgrade() -> None:
    for column in ("is_active", "pos_y", "pos_x", "shape", "zone"):
        op.drop_column("restaurant_tables", column)
