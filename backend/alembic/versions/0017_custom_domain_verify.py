"""Custom domain verification (mocked for now)

Revision ID: 0017_custom_domain_verify
Revises: 0016_reservation_guest_confirm
Create Date: 2026-10-01

Expand step only: one nullable column. Real DNS/TLS automation is a later step (see ROADMAP, Stage E);
today "verifying" a domain is a platform-admin action that just sets this timestamp.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0017_custom_domain_verify"
down_revision: Union[str, None] = "0016_reservation_guest_confirm"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("restaurants", sa.Column("domain_verified_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("restaurants", "domain_verified_at")
