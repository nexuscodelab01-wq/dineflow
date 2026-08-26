"""Initial baseline migration (no domain tables yet).

Revision ID: 0001_baseline
Revises:
Create Date: 2026-08-24 00:00:00.000000

"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "0001_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Domain tables are introduced in Phase 2.
    pass


def downgrade() -> None:
    pass
