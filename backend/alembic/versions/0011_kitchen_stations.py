"""Kitchen stations and item-level status

Revision ID: 0011_kitchen_stations
Revises: 0010_service_requests
Create Date: 2026-09-25

Expand step only: new columns with defaults. Existing dishes are given a sensible station from their
category name (drinks -> BAR, desserts -> DESSERT, everything else stays KITCHEN); order lines of orders that
are already finished are marked READY so no old ticket looks unfinished.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0011_kitchen_stations"
down_revision: Union[str, None] = "0010_service_requests"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("menu_items", sa.Column("station", sa.String(20), server_default="KITCHEN", nullable=False))
    op.add_column("order_items", sa.Column("station", sa.String(20), server_default="KITCHEN", nullable=False))
    op.add_column("order_items", sa.Column("status", sa.String(10), server_default="NEW", nullable=False))
    op.add_column("order_items", sa.Column("ready_at", sa.DateTime(timezone=True), nullable=True))

    op.execute("""
        UPDATE menu_items SET station = 'BAR'
        WHERE category_id IN (SELECT id FROM categories WHERE name ~* '(drink|beverage|coffee|cocktail|wine|beer|bar)')
    """)
    op.execute("""
        UPDATE menu_items SET station = 'DESSERT'
        WHERE category_id IN (SELECT id FROM categories WHERE name ~* '(dessert|sweet)')
    """)
    op.execute("UPDATE order_items SET station = m.station FROM menu_items m WHERE order_items.menu_item_id = m.id")
    op.execute("""
        UPDATE order_items SET status = 'READY', ready_at = now()
        WHERE order_id IN (SELECT id FROM orders WHERE status NOT IN ('PENDING', 'CONFIRMED', 'PREPARING'))
           OR order_id IN (SELECT id FROM orders WHERE status = 'READY')
    """)


def downgrade() -> None:
    op.drop_column("order_items", "ready_at")
    op.drop_column("order_items", "status")
    op.drop_column("order_items", "station")
    op.drop_column("menu_items", "station")
