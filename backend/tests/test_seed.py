"""Regression test for db/seed.py's full first-run path — creating a restaurant with menu, orders and
payments from scratch. Nothing else in the suite ever exercises this: every other test either calls
FeatureService(db).ensure_defaults()/RoleRepository(db).ensure_defaults() directly (conftest.py's `db`
fixture) or builds its own tenant via tests/tenants.py's make_tenant, so seed()'s own order-creation path
had zero coverage — which is exactly how a NOT NULL violation (payments.restaurant_id, added back in the
Stripe Connect migration) sat undetected until the very first real production deploy hit a genuinely
empty database and seed() ran for real."""

from app.db import seed as seed_module
from app.models.payment import Payment
from app.models.restaurant import Restaurant


class _NoCloseSession:
    """Lets seed() use the test's own rolled-back transaction — its db.close() becomes a no-op so the
    `db` fixture's own teardown (rollback + close) still happens exactly once. Same idea as
    test_features.py's _Ctx, adapted for seed()'s plain `db = SessionLocal(); ...; db.close()` shape
    rather than a `with` block."""

    def __init__(self, db):
        self._db = db

    def __getattr__(self, name):
        return getattr(self._db, name)

    def close(self):
        pass


def test_seeding_a_genuinely_empty_database_succeeds(db, monkeypatch):
    monkeypatch.setattr(seed_module, "SessionLocal", lambda: _NoCloseSession(db))

    seed_module.seed()  # must not raise — this is the exact path that crashed in production

    restaurant = db.query(Restaurant).filter_by(slug="bella-vista-kitchen").one()
    payments = db.query(Payment).filter_by(restaurant_id=restaurant.id).all()
    assert payments, "seed() should have created at least one payment for its demo orders"
    assert all(p.restaurant_id == restaurant.id for p in payments)


def test_seeding_twice_is_idempotent(db, monkeypatch):
    monkeypatch.setattr(seed_module, "SessionLocal", lambda: _NoCloseSession(db))

    seed_module.seed()
    seed_module.seed()  # a second run (e.g. a container restart) must not try to recreate anything

    assert db.query(Restaurant).filter_by(slug="bella-vista-kitchen").count() == 1
