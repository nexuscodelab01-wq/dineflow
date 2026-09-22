"""Guest confirmation on a reservation

Revision ID: 0016_reservation_guest_confirm
Revises: 0015_guest_profiles
Create Date: 2026-09-30

Expand step only: one nullable column, set when a guest taps "I'll be there" from a reminder email
(the link itself is a signed, stateless token — nothing else to store for it).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0016_reservation_guest_confirm"
down_revision: Union[str, None] = "0015_guest_profiles"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("reservations", sa.Column("guest_confirmed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("reservations", "guest_confirmed_at")
