"""Device.kind — till vs handheld

Revision ID: 0037_device_kind
Revises: 0036_table_session_party_size
Create Date: 2026-10-21

What a device is *for*: whether it owns a cash drawer (TILL: mandatory shift + starting float) or is carried
by a server (HANDHELD: no drawer, no float gate). Defaults to TILL so every already-paired device keeps
behaving exactly as it did.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0037_device_kind"
down_revision: Union[str, None] = "0036_table_session_party_size"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("devices", sa.Column("kind", sa.String(length=10), server_default="TILL", nullable=False))


def downgrade() -> None:
    op.drop_column("devices", "kind")
