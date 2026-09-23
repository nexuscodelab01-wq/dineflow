"""Home page content: about us, gallery, social links, map coordinates

Revision ID: 0023_home_page_content
Revises: 0022_table_combining
Create Date: 2026-09-24

Expand step only: nullable/defaulted columns. An existing restaurant gets no gallery, no social
links and no map — the home page falls back to what it shows today (name, logo, description,
address as plain text).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0023_home_page_content"
down_revision: Union[str, None] = "0022_table_combining"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("restaurants", sa.Column("about_text", sa.Text(), nullable=True))
    op.add_column("restaurants", sa.Column("gallery", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False))
    op.add_column("restaurants", sa.Column("social_links", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False))
    op.add_column("restaurants", sa.Column("latitude", sa.Numeric(9, 6), nullable=True))
    op.add_column("restaurants", sa.Column("longitude", sa.Numeric(9, 6), nullable=True))


def downgrade() -> None:
    op.drop_column("restaurants", "longitude")
    op.drop_column("restaurants", "latitude")
    op.drop_column("restaurants", "social_links")
    op.drop_column("restaurants", "gallery")
    op.drop_column("restaurants", "about_text")
