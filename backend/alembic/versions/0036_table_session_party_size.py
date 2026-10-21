"""TableSession.party_size — staff-seated walk-ins

Revision ID: 0036_table_session_party_size
Revises: 0035_employee_attribution
Create Date: 2026-10-21

A nullable `party_size` on `table_sessions`, set only when staff seat a walk-in directly from the POS
(`TableSessionService.open_for_staff`) — no one scanned, so there's no `SessionGuest` row to count. The
guest-QR join path never sets this; its guest count still comes from counting `SessionGuest` rows.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0036_table_session_party_size"
down_revision: Union[str, None] = "0035_employee_attribution"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("table_sessions", sa.Column("party_size", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("table_sessions", "party_size")
