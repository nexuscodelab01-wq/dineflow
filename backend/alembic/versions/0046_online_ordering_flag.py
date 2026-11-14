"""The online_ordering feature flag (on by default)

Revision ID: 0046_online_ordering_flag
Revises: 0045_bar_tabs
Create Date: 2026-11-13

Customers' cart, checkout and online orders can now be switched off per restaurant (a restaurant that only wants its menu
shown). The flag is created HERE, enabled by default, so every existing restaurant keeps ordering exactly as before the
moment this migration runs — never depending on the start-up bootstrap having run first.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0046_online_ordering_flag"
down_revision: Union[str, None] = "0045_bar_tabs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "INSERT INTO features (key, description, default_enabled) VALUES "
        "('online_ordering', 'Customers can order online: cart, checkout, pickup and delivery. Off = the site only shows the menu', true) "
        "ON CONFLICT (key) DO NOTHING"
    )


def downgrade() -> None:
    op.execute("DELETE FROM feature_overrides WHERE key = 'online_ordering'")
    op.execute("DELETE FROM features WHERE key = 'online_ordering'")
