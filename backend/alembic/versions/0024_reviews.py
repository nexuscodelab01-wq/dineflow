"""Guest reviews

Revision ID: 0024_reviews
Revises: 0023_home_page_content
Create Date: 2026-09-23

New tenant table, so it needs a row-level security policy of its own (same shape as waitlist_entries'
in 0020_waitlist) — otherwise tests/test_row_level_security.py::test_every_tenant_table_has_a_policy fails.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0024_reviews"
down_revision: Union[str, None] = "0023_home_page_content"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "reviews",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("restaurant_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=True),
        sa.Column("reservation_id", sa.Integer(), nullable=True),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("is_published", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("staff_reply", sa.Text(), nullable=True),
        sa.Column("staff_reply_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["restaurant_id"], ["restaurants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reservation_id"], ["reservations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("rating >= 1 AND rating <= 5", name="ck_reviews_rating_range"),
        sa.CheckConstraint(
            "(order_id IS NOT NULL)::int + (reservation_id IS NOT NULL)::int = 1",
            name="ck_reviews_one_visit",
        ),
        sa.UniqueConstraint("restaurant_id", "order_id", name="uq_reviews_order"),
        sa.UniqueConstraint("restaurant_id", "reservation_id", name="uq_reviews_reservation"),
    )
    op.create_index(op.f("ix_reviews_restaurant_id"), "reviews", ["restaurant_id"], unique=False)
    op.create_index(op.f("ix_reviews_user_id"), "reviews", ["user_id"], unique=False)

    op.execute("ALTER TABLE reviews ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON reviews "
        "USING (app_rls_off() OR restaurant_id = app_rls_tenant()) "
        "WITH CHECK (app_rls_off() OR restaurant_id = app_rls_tenant())"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON reviews")
    op.drop_index(op.f("ix_reviews_user_id"), table_name="reviews")
    op.drop_index(op.f("ix_reviews_restaurant_id"), table_name="reviews")
    op.drop_table("reviews")
