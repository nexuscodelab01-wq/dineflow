"""Row-level security: PostgreSQL keeps each restaurant's rows apart

Revision ID: 0013_row_level_security
Revises: 0012_password_reset
Create Date: 2026-09-27

Adds a policy to every tenant table. A transaction in *tenant mode* (session settings `app.rls_mode = 'tenant'` and
`app.tenant_id = <restaurant id>`, set by the app for staff, signed-in customers and table guests) can only see and
change that restaurant's rows, whatever the SQL says. In any other mode (the default: sign-in, public menus, jobs, the
CLI) the policies let everything through, so nothing changes for those paths.

Policies apply to ordinary roles only: the table owner (which runs migrations) is not restricted, and the app is meant
to connect as the restricted `dineflow_app` role (see app/db/roles.py and docs/OPERATIONS.md). No data changes.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0013_row_level_security"
down_revision: Union[str, None] = "0012_password_reset"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OFF = "app_rls_off()"
TENANT = "app_rls_tenant()"

# Tables with a restaurant_id: the row must belong to the current restaurant...
STRICT = [
    "categories", "feature_overrides", "menu_items", "menu_modifiers", "orders", "reservations",
    "restaurant_tables", "restaurant_users", "service_requests", "table_sessions",
]
# ...or, where NULL means "not about one restaurant" (platform staff, global jobs, platform audit entries), be NULL.
NULLABLE = ["audit_log", "jobs", "password_reset_tokens", "users"]
# Tables that belong to a parent row: visible exactly when the parent is (the parent's own policy applies inside).
CHILDREN = {
    "menu_item_modifiers": ("menu_item_id", "menu_items"),
    "menu_modifier_options": ("modifier_id", "menu_modifiers"),
    "order_items": ("order_id", "orders"),
    "order_item_modifiers": ("order_item_id", "order_items"),
    "order_status_history": ("order_id", "orders"),
    "payments": ("order_id", "orders"),
    "session_guests": ("session_id", "table_sessions"),
    "addresses": ("user_id", "users"),
}


def _policy(table: str, predicate: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY tenant_isolation ON {table} USING ({predicate}) WITH CHECK ({predicate})")


def upgrade() -> None:
    op.execute("""
        CREATE FUNCTION app_rls_off() RETURNS boolean LANGUAGE sql STABLE AS
        $$ SELECT coalesce(current_setting('app.rls_mode', true), '') <> 'tenant' $$
    """)
    op.execute("""
        CREATE FUNCTION app_rls_tenant() RETURNS integer LANGUAGE sql STABLE AS
        $$ SELECT nullif(current_setting('app.tenant_id', true), '')::integer $$
    """)
    for table in STRICT:
        _policy(table, f"{OFF} OR restaurant_id = {TENANT}")
    for table in NULLABLE:
        _policy(table, f"{OFF} OR restaurant_id IS NULL OR restaurant_id = {TENANT}")
    _policy("restaurants", f"{OFF} OR id = {TENANT}")
    for table, (column, parent) in CHILDREN.items():
        _policy(table, f"{OFF} OR EXISTS (SELECT 1 FROM {parent} p WHERE p.id = {table}.{column})")


def downgrade() -> None:
    for table in [*STRICT, *NULLABLE, "restaurants", *CHILDREN]:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.execute("DROP FUNCTION IF EXISTS app_rls_tenant()")
    op.execute("DROP FUNCTION IF EXISTS app_rls_off()")
