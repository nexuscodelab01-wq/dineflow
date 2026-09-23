"""Guest booking policy: party size limits and lead time

Revision ID: 0019_booking_policy
Revises: 0018_secondary_color
Create Date: 2026-09-23

Expand step only: three columns with defaults that reproduce today's behaviour (party size 1+,
no maximum, no minimum notice), so every existing restaurant is unaffected until a policy is set.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0019_booking_policy"
down_revision: Union[str, None] = "0018_secondary_color"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("restaurants", sa.Column("min_party_size", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("restaurants", sa.Column("max_party_size", sa.Integer(), nullable=True))
    op.add_column("restaurants", sa.Column("booking_lead_time_minutes", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("restaurants", "booking_lead_time_minutes")
    op.drop_column("restaurants", "max_party_size")
    op.drop_column("restaurants", "min_party_size")
