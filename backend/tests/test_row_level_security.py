"""Row-level security: PostgreSQL itself keeps each restaurant's rows apart for the restricted app role.

These tests connect as the restricted role directly, so they hold whichever role the rest of the suite runs as.
"""

import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.roles import ensure_app_role
from app.db.session import enter_bypass_mode, enter_tenant_mode

ROLE_PASSWORD = "rls_test_password"
# Tables that are intentionally not tenant-scoped (global reference data, or auth internals only ever read by id/hash).
UNSCOPED = {"alembic_version", "roles", "refresh_tokens"}


@pytest.fixture(scope="module")
def app_engine():
    owner = make_url(settings.DATABASE_URL)
    app_url = owner.set(username="dineflow_rls_test", password=ROLE_PASSWORD).render_as_string(hide_password=False)
    ensure_app_role(settings.DATABASE_URL, app_url)
    engine = create_engine(app_url)
    yield engine
    engine.dispose()


@pytest.fixture
def two_restaurants(app_engine):
    """Two restaurants with a category each, written as the restricted role in a transaction that is rolled back."""
    connection = app_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint", autoflush=False)
    tag = uuid.uuid4().hex[:8]
    ids = {}
    for label in ("a", "b"):
        rid = session.execute(text(
            "INSERT INTO restaurants (name, slug, order_prefix, next_order_number, is_active, delivery_enabled, pickup_enabled, dine_in_enabled,"
            " tax_rate, delivery_fee, reservation_buffer_minutes, qr_access_policy, created_at, updated_at)"
            " VALUES (:n, :s, 'RL', 1001, true, true, true, true, 0.1, 1, 15, 'SEATED', now(), now()) RETURNING id"),
            {"n": f"RLS {label}", "s": f"rls-{label}-{tag}"}).scalar()
        cid = session.execute(text("INSERT INTO categories (restaurant_id, name, slug, sort_order, is_active, created_at, updated_at) "
                                   "VALUES (:r, :n, :s, 0, true, now(), now()) RETURNING id"), {"r": rid, "n": f"Cat {label}", "s": f"cat-{label}"}).scalar()
        session.execute(text("INSERT INTO jobs (type, payload, restaurant_id) VALUES ('noop', '{}'::jsonb, :r)"), {"r": rid})
        ids[label] = {"restaurant": rid, "category": cid}
    session.execute(text("INSERT INTO audit_log (restaurant_id, actor_label, action, details) VALUES (NULL, 'platform', 'x', '{}'::jsonb)"))
    session.flush()
    yield session, ids
    session.close()
    transaction.rollback()
    connection.close()


def visible(session, sql, **params):
    return session.execute(text(sql), params).scalars().all()


# ------------------------------------------------------------------ the role

def test_the_app_role_cannot_bypass_row_level_security(app_engine):
    with app_engine.connect() as conn:
        who, sup, bypass = conn.execute(text(
            "SELECT current_user, r.rolsuper, r.rolbypassrls FROM pg_roles r WHERE r.rolname = current_user")).one()
    assert who == "dineflow_rls_test" and sup is False and bypass is False


def test_every_tenant_table_has_a_policy():
    """A table with a restaurant_id column, or added later without one, must not slip past row-level security."""
    engine = create_engine(settings.DATABASE_URL)
    with engine.connect() as conn:
        tables = conn.execute(text(
            "SELECT c.relname, c.relrowsecurity, EXISTS (SELECT 1 FROM pg_policy p WHERE p.polrelid = c.oid) "
            "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'public' AND c.relkind = 'r'")).all()
        scoped = {r[0] for r in conn.execute(text(
            "SELECT table_name FROM information_schema.columns WHERE table_schema = 'public' AND column_name = 'restaurant_id'"))}
    engine.dispose()
    unprotected = [name for name, on, has_policy in tables if name not in UNSCOPED and not (on and has_policy)]
    assert not unprotected, f"Tables without a row-level security policy: {unprotected}. Add one in a migration (or list it in UNSCOPED with a reason)."
    assert scoped <= {name for name, on, has_policy in tables if on and has_policy}


# ------------------------------------------------------------------ what a tenant can see

def test_in_bypass_mode_nothing_is_hidden(two_restaurants):
    session, ids = two_restaurants
    assert set(visible(session, "SELECT id FROM restaurants WHERE id IN (:a, :b)", a=ids["a"]["restaurant"], b=ids["b"]["restaurant"])) == {ids["a"]["restaurant"], ids["b"]["restaurant"]}


def test_in_tenant_mode_only_that_restaurants_rows_are_visible(two_restaurants):
    session, ids = two_restaurants
    enter_tenant_mode(session, ids["a"]["restaurant"])
    assert visible(session, "SELECT id FROM restaurants") == [ids["a"]["restaurant"]]
    assert visible(session, "SELECT id FROM categories") == [ids["a"]["category"]]
    assert visible(session, "SELECT restaurant_id FROM jobs") == [ids["a"]["restaurant"]]
    assert visible(session, "SELECT actor_label FROM audit_log") == ["platform"]              # rows about no restaurant stay visible
    enter_tenant_mode(session, ids["b"]["restaurant"])
    assert visible(session, "SELECT id FROM categories") == [ids["b"]["category"]]


def test_a_forgotten_where_clause_cannot_leak_other_restaurants(two_restaurants):
    """The point of the safety net: the query below has no restaurant filter at all."""
    session, ids = two_restaurants
    enter_tenant_mode(session, ids["a"]["restaurant"])
    assert visible(session, "SELECT name FROM categories WHERE name LIKE 'Cat %'") == ["Cat a"]
    assert visible(session, "SELECT count(*) FROM categories WHERE restaurant_id = :b", b=ids["b"]["restaurant"]) == [0]


def test_a_tenant_session_without_a_restaurant_sees_nothing(two_restaurants):
    session, _ = two_restaurants
    session.execute(text("SELECT set_config('app.rls_mode', 'tenant', true), set_config('app.tenant_id', '', true)"))
    assert visible(session, "SELECT id FROM restaurants") == [] and visible(session, "SELECT id FROM categories") == []


def test_going_back_to_bypass_restores_full_access(two_restaurants):
    session, ids = two_restaurants
    enter_tenant_mode(session, ids["a"]["restaurant"])
    enter_bypass_mode(session)
    assert len(visible(session, "SELECT id FROM restaurants WHERE id IN (:a, :b)", a=ids["a"]["restaurant"], b=ids["b"]["restaurant"])) == 2


# ------------------------------------------------------------------ what a tenant can change

def test_a_tenant_cannot_write_into_or_touch_another_restaurant(two_restaurants):
    session, ids = two_restaurants
    a, b = ids["a"], ids["b"]
    enter_tenant_mode(session, a["restaurant"])

    with pytest.raises(DBAPIError, match="row-level security"), session.begin_nested():       # insert into another restaurant
        session.execute(text("INSERT INTO categories (restaurant_id, name, slug, sort_order, is_active, created_at, updated_at) "
                             "VALUES (:r, 'Sneaky', 'sneaky', 0, true, now(), now())"), {"r": b["restaurant"]})
    with pytest.raises(DBAPIError, match="row-level security"), session.begin_nested():       # hand one of our rows to another restaurant
        session.execute(text("UPDATE categories SET restaurant_id = :r WHERE id = :c"), {"r": b["restaurant"], "c": a["category"]})

    assert session.execute(text("UPDATE categories SET name = 'Hacked' WHERE id = :c"), {"c": b["category"]}).rowcount == 0
    assert session.execute(text("DELETE FROM categories WHERE id = :c"), {"c": b["category"]}).rowcount == 0
    assert session.execute(text("UPDATE restaurants SET name = 'Hacked' WHERE id = :r"), {"r": b["restaurant"]}).rowcount == 0
    enter_bypass_mode(session)
    assert visible(session, "SELECT name FROM categories WHERE id = :c", c=b["category"]) == ["Cat b"]


def test_the_role_cannot_switch_the_policies_off(two_restaurants):
    session, ids = two_restaurants
    enter_tenant_mode(session, ids["a"]["restaurant"])
    with pytest.raises(DBAPIError), session.begin_nested():
        session.execute(text("SET LOCAL row_security = off"))
        session.execute(text("SELECT id FROM categories")).all()


# ------------------------------------------------------------------ the restriction survives commits and pooled connections

def test_tenant_mode_survives_commits_and_never_leaks_to_the_next_user_of_a_connection(app_engine):
    owner = create_engine(settings.DATABASE_URL)
    tag = uuid.uuid4().hex[:8]
    made = []
    with owner.begin() as conn:
        for label in ("a", "b"):
            made.append(conn.execute(text(
                "INSERT INTO restaurants (name, slug, order_prefix, next_order_number, is_active, delivery_enabled, pickup_enabled, dine_in_enabled,"
                " tax_rate, delivery_fee, reservation_buffer_minutes, qr_access_policy, created_at, updated_at)"
                " VALUES (:n, :s, 'RL', 1001, true, true, true, true, 0.1, 1, 15, 'SEATED', now(), now()) RETURNING id"),
                {"n": f"Commit {label}", "s": f"commit-{label}-{tag}"}).scalar())
    try:
        session = Session(bind=app_engine, autoflush=False)
        enter_tenant_mode(session, made[0])
        assert visible(session, "SELECT id FROM restaurants WHERE slug LIKE :p", p=f"commit-%-{tag}") == [made[0]]
        session.commit()                                                                       # a new transaction starts…
        assert visible(session, "SELECT id FROM restaurants WHERE slug LIKE :p", p=f"commit-%-{tag}") == [made[0]]   # …still restricted
        session.commit()
        session.close()

        fresh = Session(bind=app_engine, autoflush=False)                                       # the pooled connection is reused
        assert set(visible(fresh, "SELECT id FROM restaurants WHERE slug LIKE :p", p=f"commit-%-{tag}")) == set(made)   # …without the restriction
        fresh.close()
    finally:
        with owner.begin() as conn:
            conn.execute(text("DELETE FROM restaurants WHERE id = ANY(:ids)"), {"ids": made})
        owner.dispose()
