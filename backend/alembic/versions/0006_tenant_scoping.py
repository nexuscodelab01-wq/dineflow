"""Scope users and order numbers to a restaurant (tenant)

Revision ID: 0006_tenant_scoping
Revises: 0005_jobs
Create Date: 2026-09-22

Customers now belong to one restaurant, so the same email can be a customer of two restaurants
without the accounts being linked. Staff and platform admins stay "global" identities
(restaurant_id NULL) and reach restaurants through memberships.

Expand step only: nothing is dropped except the two global unique indexes that these changes replace.
"""
import re
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0006_tenant_scoping"
down_revision: Union[str, None] = "0005_jobs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _prefix(name: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", name or "")
    initials = "".join(w[0] for w in words)[:4].upper()
    return initials if len(initials) >= 2 else (re.sub(r"[^A-Za-z0-9]", "", name or "")[:3].upper() or "DF")


def upgrade() -> None:
    bind = op.get_bind()

    # ---- users: customers belong to a restaurant -------------------------------------------
    op.add_column("users", sa.Column("restaurant_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_users_restaurant_id", "users", "restaurants", ["restaurant_id"], ["id"], ondelete="CASCADE")
    op.create_index("ix_users_restaurant_id", "users", ["restaurant_id"])

    # Existing customers go to the restaurant they actually used most; anyone with no activity goes to
    # the first restaurant (today there is only one). Staff/admins keep restaurant_id NULL.
    op.execute(
        """
        UPDATE users u SET restaurant_id = COALESCE(
            (SELECT o.restaurant_id FROM orders o WHERE o.user_id = u.id
             GROUP BY o.restaurant_id ORDER BY count(*) DESC, o.restaurant_id LIMIT 1),
            (SELECT r.restaurant_id FROM reservations r WHERE r.user_id = u.id
             GROUP BY r.restaurant_id ORDER BY count(*) DESC, r.restaurant_id LIMIT 1),
            (SELECT MIN(id) FROM restaurants)
        )
        FROM roles ro WHERE ro.id = u.role_id AND ro.name = 'CUSTOMER'
        """
    )

    # Email is unique per restaurant for customers, and unique among global identities.
    op.drop_index("ix_users_email", table_name="users")
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index(
        "uq_users_tenant_email", "users", ["restaurant_id", "email"], unique=True,
        postgresql_where=sa.text("restaurant_id IS NOT NULL"),
    )
    op.create_index(
        "uq_users_global_email", "users", ["email"], unique=True,
        postgresql_where=sa.text("restaurant_id IS NULL"),
    )

    # ---- restaurants: custom domain, order numbering ---------------------------------------
    op.add_column("restaurants", sa.Column("custom_domain", sa.String(length=253), nullable=True))
    op.create_index("uq_restaurants_custom_domain", "restaurants", ["custom_domain"], unique=True)
    op.add_column("restaurants", sa.Column("order_prefix", sa.String(length=8), server_default="DF", nullable=False))
    op.add_column("restaurants", sa.Column("next_order_number", sa.Integer(), server_default="1001", nullable=False))
    for row in bind.execute(sa.text("SELECT id, name FROM restaurants")).all():
        bind.execute(sa.text("UPDATE restaurants SET order_prefix = :p WHERE id = :i"), {"p": _prefix(row.name), "i": row.id})

    # ---- orders: numbers are unique per restaurant, not globally ---------------------------
    op.drop_index("ix_orders_order_number", table_name="orders")
    op.create_index("ix_orders_order_number", "orders", ["order_number"])
    op.create_unique_constraint("uq_orders_restaurant_number", "orders", ["restaurant_id", "order_number"])


def downgrade() -> None:
    op.drop_constraint("uq_orders_restaurant_number", "orders", type_="unique")
    op.drop_index("ix_orders_order_number", table_name="orders")
    op.create_index("ix_orders_order_number", "orders", ["order_number"], unique=True)

    op.drop_column("restaurants", "next_order_number")
    op.drop_column("restaurants", "order_prefix")
    op.drop_index("uq_restaurants_custom_domain", table_name="restaurants")
    op.drop_column("restaurants", "custom_domain")

    op.drop_index("uq_users_global_email", table_name="users")
    op.drop_index("uq_users_tenant_email", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.drop_index("ix_users_restaurant_id", table_name="users")
    op.drop_constraint("fk_users_restaurant_id", "users", type_="foreignkey")
    op.drop_column("users", "restaurant_id")
