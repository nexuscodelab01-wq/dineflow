"""Feature flag catalog moves from code into the database

Revision ID: 0032_feature_catalog
Revises: 0031_pay_at_table
Create Date: 2026-10-05

Schema only — no data. The 9 flags that used to live in the hardcoded `FEATURES` dict
(backend/app/core/features.py, now deleted) are seeded idempotently by `FeatureService.ensure_defaults()`,
called from `db/seed.py` and `tests/conftest.py`, the same pattern already used for `Role`
(`RoleRepository.ensure_defaults()`) — not baked in here, since these rows are meant to be created and
deleted afterward by a platform admin, unlike ordinary migration history.

A platform-wide reference table, like `roles`: no restaurant_id, no row-level-security policy (see
migration 0013's own `roles` precedent).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0032_feature_catalog"
down_revision: Union[str, None] = "0031_pay_at_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "features",
        sa.Column("key", sa.String(length=64), primary_key=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("default_enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("features")
