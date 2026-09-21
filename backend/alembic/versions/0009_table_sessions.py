"""QR table ordering: table tokens, shared table sessions, guest orders

Revision ID: 0009_table_sessions
Revises: 0008_brand_color
Create Date: 2026-09-23

Expand step only: new tables and nullable columns, plus one loosened constraint (orders.customer_email
may now be empty, because a guest at a table has no email). Existing tables get a random QR token.
"""
import secrets
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0009_table_sessions"
down_revision: Union[str, None] = "0008_brand_color"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("restaurant_tables", sa.Column("qr_token", sa.String(32), nullable=True))
    conn = op.get_bind()
    for (table_id,) in conn.execute(sa.text("SELECT id FROM restaurant_tables")).all():
        conn.execute(sa.text("UPDATE restaurant_tables SET qr_token = :t WHERE id = :i"), {"t": secrets.token_urlsafe(16), "i": table_id})
    op.create_index("ix_restaurant_tables_qr_token", "restaurant_tables", ["qr_token"], unique=True)

    op.add_column("restaurants", sa.Column("qr_access_policy", sa.String(10), server_default="SEATED", nullable=False))

    op.create_table(
        "table_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("table_id", sa.Integer(), sa.ForeignKey("restaurant_tables.id", ondelete="CASCADE"), nullable=False),
        sa.Column("state", sa.String(10), server_default="OPEN", nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_table_sessions_restaurant_id", "table_sessions", ["restaurant_id"])
    op.create_index("ix_table_sessions_table_id", "table_sessions", ["table_id"])
    op.create_index("uq_table_sessions_one_open", "table_sessions", ["table_id"], unique=True, postgresql_where=sa.text("state = 'OPEN'"))

    op.create_table(
        "session_guests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("table_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_session_guests_session_id", "session_guests", ["session_id"])

    op.add_column("orders", sa.Column("table_session_id", sa.Integer(), sa.ForeignKey("table_sessions.id", ondelete="SET NULL"), nullable=True))
    op.add_column("orders", sa.Column("session_guest_id", sa.Integer(), sa.ForeignKey("session_guests.id", ondelete="SET NULL"), nullable=True))
    op.add_column("orders", sa.Column("round_no", sa.Integer(), nullable=True))
    op.add_column("orders", sa.Column("client_token", sa.String(64), nullable=True))
    op.create_index("ix_orders_table_session_id", "orders", ["table_session_id"])
    op.create_index(
        "uq_orders_session_client_token", "orders", ["table_session_id", "client_token"], unique=True,
        postgresql_where=sa.text("client_token IS NOT NULL"),
    )
    op.alter_column("orders", "customer_email", existing_type=sa.String(255), nullable=True)


def downgrade() -> None:
    op.execute("UPDATE orders SET customer_email = '' WHERE customer_email IS NULL")
    op.alter_column("orders", "customer_email", existing_type=sa.String(255), nullable=False)
    op.drop_index("uq_orders_session_client_token", table_name="orders")
    op.drop_index("ix_orders_table_session_id", table_name="orders")
    for column in ("client_token", "round_no", "session_guest_id", "table_session_id"):
        op.drop_column("orders", column)
    op.drop_index("ix_session_guests_session_id", table_name="session_guests")
    op.drop_table("session_guests")
    op.drop_index("uq_table_sessions_one_open", table_name="table_sessions")
    op.drop_index("ix_table_sessions_table_id", table_name="table_sessions")
    op.drop_index("ix_table_sessions_restaurant_id", table_name="table_sessions")
    op.drop_table("table_sessions")
    op.drop_column("restaurants", "qr_access_policy")
    op.drop_index("ix_restaurant_tables_qr_token", table_name="restaurant_tables")
    op.drop_column("restaurant_tables", "qr_token")
