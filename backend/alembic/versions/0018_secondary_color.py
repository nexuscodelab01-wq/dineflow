"""Restaurant secondary (accent) colour

Revision ID: 0018_secondary_color
Revises: 0017_custom_domain_verify
Create Date: 2026-10-02

Expand step only: one nullable column, same shape as primary_color. Optional — a restaurant with none
set gets its accent colour derived from the primary one, same as before this existed.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0018_secondary_color"
down_revision: Union[str, None] = "0017_custom_domain_verify"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("restaurants", sa.Column("secondary_color", sa.String(7), nullable=True))


def downgrade() -> None:
    op.drop_column("restaurants", "secondary_color")
