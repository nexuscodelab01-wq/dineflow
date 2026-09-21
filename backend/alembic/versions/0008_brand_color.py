"""Restaurant brand colour

Revision ID: 0008_brand_color
Revises: 0007_feature_flags
Create Date: 2026-09-22

Expand step only: one nullable column. The site derives its palette from it.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0008_brand_color"
down_revision: Union[str, None] = "0007_feature_flags"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("restaurants", sa.Column("primary_color", sa.String(7), nullable=True))


def downgrade() -> None:
    op.drop_column("restaurants", "primary_color")
