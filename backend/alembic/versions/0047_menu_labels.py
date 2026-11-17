"""Restaurant-defined allergens and dish types

Revision ID: 0047_menu_labels
Revises: 0046_online_ordering_flag
Create Date: 2026-11-16

`menu_labels` is a new tenant table, so it gets a row-level security policy of its own (same shape as coupons in
0026) — otherwise tests/test_row_level_security.py::test_every_tenant_table_has_a_policy fails.

Every EXISTING restaurant is given the standard 14 allergens, so nothing changes for it until an owner edits the list
(`restaurants.labels_seeded` is then true). New restaurants are seeded the first time their labels are read.
`menu_items.tags` holds a dish's dish-type codes, the same JSONB-list pattern as `menu_items.allergens`.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0047_menu_labels"
down_revision: Union[str, None] = "0046_online_ordering_flag"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Frozen copy of app.core.allergens.ALLERGENS at the time of writing (a migration must not follow later edits).
STANDARD_ALLERGENS = [
    ("celery", "Celery"),
    ("cereals_gluten", "Cereals containing gluten"),
    ("crustaceans", "Crustaceans"),
    ("eggs", "Eggs"),
    ("fish", "Fish"),
    ("lupin", "Lupin"),
    ("milk", "Milk"),
    ("molluscs", "Molluscs"),
    ("mustard", "Mustard"),
    ("nuts", "Tree nuts"),
    ("peanuts", "Peanuts"),
    ("sesame", "Sesame"),
    ("soybeans", "Soybeans"),
    ("sulphites", "Sulphur dioxide / sulphites"),
]


def upgrade() -> None:
    op.create_table(
        "menu_labels",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("restaurant_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("code", sa.String(length=60), nullable=False),
        sa.Column("label", sa.String(length=60), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["restaurant_id"], ["restaurants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("restaurant_id", "kind", "code", name="uq_menu_label_restaurant_kind_code"),
        sa.CheckConstraint("kind IN ('allergen', 'dish_type')", name="ck_menu_labels_kind"),
    )
    op.create_index(op.f("ix_menu_labels_restaurant_id"), "menu_labels", ["restaurant_id"], unique=False)
    op.execute("ALTER TABLE menu_labels ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON menu_labels "
        "USING (app_rls_off() OR restaurant_id = app_rls_tenant()) "
        "WITH CHECK (app_rls_off() OR restaurant_id = app_rls_tenant())"
    )

    op.add_column("menu_items", sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False))
    op.add_column("restaurants", sa.Column("labels_seeded", sa.Boolean(), server_default="false", nullable=False))

    for position, (code, label) in enumerate(STANDARD_ALLERGENS):
        op.execute(
            sa.text(
                "INSERT INTO menu_labels (restaurant_id, kind, code, label, sort_order) "
                "SELECT id, 'allergen', :code, :label, :pos FROM restaurants"
            ).bindparams(code=code, label=label, pos=position)
        )
    op.execute("UPDATE restaurants SET labels_seeded = true")


def downgrade() -> None:
    op.drop_column("restaurants", "labels_seeded")
    op.drop_column("menu_items", "tags")
    op.drop_table("menu_labels")
