"""Restaurant.country

Revision ID: 0038_restaurant_country
Revises: 0037_device_kind
Create Date: 2026-10-21

ISO 3166-1 alpha-2. Defaults to US so existing rows stay consistent with their existing usd currency.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0038_restaurant_country"
down_revision: Union[str, None] = "0037_device_kind"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("restaurants", sa.Column("country", sa.String(length=2), server_default="US", nullable=False))


def downgrade() -> None:
    op.drop_column("restaurants", "country")
