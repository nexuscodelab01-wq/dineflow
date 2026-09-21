"""Password reset and invite tokens

Revision ID: 0012_password_reset
Revises: 0011_kitchen_stations
Create Date: 2026-09-26

Expand step only: one new table. Tokens are stored hashed; each is single-use and expires.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0012_password_reset"
down_revision: Union[str, None] = "0011_kitchen_stations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurants.id", ondelete="SET NULL"), nullable=True),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("purpose", sa.String(10), server_default="RESET", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_password_reset_tokens_token_hash", "password_reset_tokens", ["token_hash"], unique=True)
    op.create_index("ix_password_reset_tokens_user_created", "password_reset_tokens", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_password_reset_tokens_user_created", table_name="password_reset_tokens")
    op.drop_index("ix_password_reset_tokens_token_hash", table_name="password_reset_tokens")
    op.drop_table("password_reset_tokens")
