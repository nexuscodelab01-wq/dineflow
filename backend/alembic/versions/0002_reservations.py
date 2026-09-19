"""Add reservations table

Revision ID: 0002_reservations
Revises: 0fc479af6358
Create Date: 2026-09-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0002_reservations"
down_revision: Union[str, None] = "0fc479af6358"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

reservation_status = postgresql.ENUM(
    "HELD",
    "CONFIRMED",
    "SEATED",
    "COMPLETED",
    "CANCELLED",
    "EXPIRED",
    name="reservation_status",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    postgresql.ENUM(
        "HELD",
        "CONFIRMED",
        "SEATED",
        "COMPLETED",
        "CANCELLED",
        "EXPIRED",
        name="reservation_status",
    ).create(bind, checkfirst=True)

    op.create_table(
        "reservations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("restaurant_id", sa.Integer(), nullable=False),
        sa.Column("table_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("order_id", sa.Integer(), nullable=True),
        sa.Column("party_size", sa.Integer(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", reservation_status, nullable=False),
        sa.Column("hold_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("guest_name", sa.String(length=200), nullable=False),
        sa.Column("guest_email", sa.String(length=255), nullable=True),
        sa.Column("guest_phone", sa.String(length=30), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["restaurant_id"], ["restaurants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["table_id"], ["restaurant_tables.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_reservations_restaurant_id"), "reservations", ["restaurant_id"], unique=False)
    op.create_index(op.f("ix_reservations_table_id"), "reservations", ["table_id"], unique=False)
    op.create_index(op.f("ix_reservations_user_id"), "reservations", ["user_id"], unique=False)
    op.create_index(op.f("ix_reservations_order_id"), "reservations", ["order_id"], unique=False)
    op.create_index(op.f("ix_reservations_starts_at"), "reservations", ["starts_at"], unique=False)
    op.create_index(op.f("ix_reservations_status"), "reservations", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_reservations_status"), table_name="reservations")
    op.drop_index(op.f("ix_reservations_starts_at"), table_name="reservations")
    op.drop_index(op.f("ix_reservations_order_id"), table_name="reservations")
    op.drop_index(op.f("ix_reservations_user_id"), table_name="reservations")
    op.drop_index(op.f("ix_reservations_table_id"), table_name="reservations")
    op.drop_index(op.f("ix_reservations_restaurant_id"), table_name="reservations")
    op.drop_table("reservations")
    postgresql.ENUM(name="reservation_status").drop(op.get_bind(), checkfirst=True)
