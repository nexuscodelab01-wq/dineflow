"""Guest profile notes on customers

Revision ID: 0015_guest_profiles
Revises: 0014_opening_hours
Create Date: 2026-09-29

Expand step only: three nullable/defaulted columns on users, only meaningful for CUSTOMER rows
(a restaurant's own notes, allergies and VIP flag on its customer).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0015_guest_profiles"
down_revision: Union[str, None] = "0014_opening_hours"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("notes", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("allergies", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("is_vip", sa.Boolean(), server_default="false", nullable=False))


def downgrade() -> None:
    op.drop_column("users", "is_vip")
    op.drop_column("users", "allergies")
    op.drop_column("users", "notes")
