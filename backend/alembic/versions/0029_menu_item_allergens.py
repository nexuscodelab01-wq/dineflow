"""Allergens on menu items and their order-time snapshot

Revision ID: 0029_menu_item_allergens
Revises: 0028_staff_membership_roles
Create Date: 2026-09-26

Adds `allergens` (a JSONB list of codes from `app.core.allergens.ALLERGENS`) to `menu_items` — the
same shape as `Restaurant.gallery` — and a second copy on `order_items`, snapshotted at order time for
the same reason `order_items.station` already is: a kitchen ticket must show what the dish contained
*when it was ordered*, not whatever the menu says by the time it's cooked. Both default to an empty
list, so this needs no backfill; a `NOT NULL` column with a `server_default` fills existing rows too.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0029_menu_item_allergens"
down_revision: Union[str, None] = "0028_staff_membership_roles"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "menu_items",
        sa.Column("allergens", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    )
    op.add_column(
        "order_items",
        sa.Column("allergens", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("order_items", "allergens")
    op.drop_column("menu_items", "allergens")
