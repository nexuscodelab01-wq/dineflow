"""Feature flags: the catalog, per-restaurant overrides, enforcement, audit trail, operator CLI."""

from datetime import datetime, timedelta, timezone

import pytest

from app import cli
from app.core.config import settings
from app.db.session import get_db
from app.main import app
from app.models.audit_log import AuditLog
from app.models.enums import RoleName
from app.services.feature_service import FeatureService
from tests.conftest import override_get_db
from tests.tenants import header, make_tenant, make_user

API = "/api/v1"


@pytest.fixture
def world(client, db):
    app.dependency_overrides[get_db] = override_get_db(db)
    boss = make_user(db, "boss@iso-demo.com", RoleName.SUPER_ADMIN)
    yield type("W", (), {"client": client, "db": db, "a": make_tenant(db, "Alpha"), "b": make_tenant(db, "Bravo"), "boss": boss})
    app.dependency_overrides.clear()


def catalog_keys(w):
    return {f.key for f in FeatureService(w.db).catalog()}


def flag_url(rid, key=""):
    return f"{API}/platform/restaurants/{rid}/features" + (f"/{key}" if key else "")


def feature_url(key=""):
    return f"{API}/platform/features" + (f"/{key}" if key else "")


def book(w, tenant):
    starts = (datetime.now(timezone.utc) + timedelta(hours=3)).replace(microsecond=0)
    return w.client.get(f"{API}/restaurants/{tenant.slug}/reservations/availability",
                        params={"starts_at": starts.isoformat(), "party_size": 2})


# ------------------------------------------------------------------ resolving

def test_flags_follow_their_defaults_until_overridden(world):
    w = world
    svc = FeatureService(w.db)
    assert svc.resolve(w.a.rid) == {f.key: f.default_enabled for f in svc.catalog()}
    svc.set(w.a.rid, "qr_table_ordering", True, w.boss)
    assert svc.resolve(w.a.rid)["qr_table_ordering"] is True
    assert svc.resolve(w.b.rid)["qr_table_ordering"] is False            # other restaurants unaffected
    svc.set(w.a.rid, "qr_table_ordering", None, w.boss)                  # reset -> back to the default
    assert svc.resolve(w.a.rid)["qr_table_ordering"] is False


def test_overrides_for_flags_deleted_from_the_catalog_are_ignored(world):
    from app.models.feature_override import FeatureOverride
    w = world
    w.db.add(FeatureOverride(restaurant_id=w.a.rid, key="long_gone", enabled=True))
    w.db.flush()
    assert "long_gone" not in FeatureService(w.db).resolve(w.a.rid)


def test_an_unknown_flag_key_resolves_as_off_rather_than_crashing(world):
    """The catalog is database-backed now, so there's no static list left to tell a code typo apart from
    "nobody's created this flag" — see feature_service.py's module docstring. Fail closed, not loud."""
    assert FeatureService(world.db).is_enabled(world.a.rid, "no-such-flag") is False


# ------------------------------------------------------------------ platform API

def test_only_platform_admins_manage_flags(world):
    w, c = world, world.client
    for who in (None, w.a.customer, w.a.staff, w.a.admin):               # even the restaurant's own admin
        h = header(who) if who else {}
        expected = 401 if who is None else 403
        assert c.get(flag_url(w.a.rid), headers=h).status_code == expected
        assert c.put(flag_url(w.a.rid, "kitchen_v2"), headers=h, json={"enabled": True}).status_code == expected
        assert c.delete(flag_url(w.a.rid, "kitchen_v2"), headers=h).status_code == expected
        assert c.get(f"{API}/platform/audit-log", headers=h).status_code == expected
    assert FeatureService(w.db).resolve(w.a.rid)["kitchen_v2"] is False


def test_platform_admin_lists_sets_resets_and_gets_clear_errors(world):
    w, c, h = world, world.client, header(world.boss)
    listing = c.get(flag_url(w.a.rid), headers=h).json()
    assert {f["key"] for f in listing} == catalog_keys(w) and all(f["override"] is None for f in listing)

    after = c.put(flag_url(w.a.rid, "pay_at_table"), headers=h, json={"enabled": True}).json()
    row = next(f for f in after if f["key"] == "pay_at_table")
    assert row["enabled"] is True and row["override"] is True and row["default"] is False

    after = c.delete(flag_url(w.a.rid, "pay_at_table"), headers=h).json()
    assert next(f for f in after if f["key"] == "pay_at_table")["override"] is None

    bad = c.put(flag_url(w.a.rid, "nope"), headers=h, json={"enabled": True})
    assert bad.status_code == 400 and "Unknown feature" in bad.json()["detail"]
    assert c.put(flag_url(999999, "kitchen_v2"), headers=h, json={"enabled": True}).status_code == 404
    assert c.get(flag_url(999999), headers=h).status_code == 404


def test_every_change_is_audited_and_no_ops_are_not(world):
    w, c, h = world, world.client, header(world.boss)
    c.put(flag_url(w.a.rid, "kitchen_v2"), headers=h, json={"enabled": True})
    c.put(flag_url(w.a.rid, "kitchen_v2"), headers=h, json={"enabled": True})      # same value again: nothing new
    c.delete(flag_url(w.a.rid, "kitchen_v2"), headers=h)
    c.put(flag_url(w.b.rid, "kitchen_v2"), headers=h, json={"enabled": False})

    rows = c.get(f"{API}/platform/audit-log", params={"restaurant_id": w.a.rid}, headers=h).json()
    assert [(r["action"], r["details"]) for r in rows] == [
        ("feature.reset", {"before": True, "after": None}),
        ("feature.set", {"before": None, "after": True}),
    ]
    assert all(r["actor_label"] == w.boss.email and r["restaurant_id"] == w.a.rid for r in rows)
    everything = c.get(f"{API}/platform/audit-log", headers=h).json()
    assert {r["restaurant_id"] for r in everything} == {w.a.rid, w.b.rid}


# ------------------------------------------------------------------ enforcement

def test_a_disabled_feature_is_refused_for_that_restaurant_only(world):
    w = world
    assert book(w, w.a.restaurant).status_code == 200 and book(w, w.b.restaurant).status_code == 200
    FeatureService(w.db).set(w.a.rid, "reservations", False, w.boss)

    off = book(w, w.a.restaurant)
    assert off.status_code == 403 and "not available" in off.json()["detail"]
    assert book(w, w.b.restaurant).status_code == 200                                  # Bravo still books

    # ...for staff and for customers creating a booking, too.
    staff_list = w.client.get(f"{API}/admin/reservations", params={"restaurant_id": w.a.rid}, headers=header(w.a.admin))
    assert staff_list.status_code == 403
    ok_b = w.client.get(f"{API}/admin/reservations", params={"restaurant_id": w.b.rid}, headers=header(w.b.admin))
    assert ok_b.status_code == 200
    made = w.client.post(f"{API}/restaurants/{w.a.slug}/reservations", headers=header(w.a.customer), json={
        "table_id": w.a.table.id, "starts_at": (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat(),
        "party_size": 2, "guest_name": "X", "guest_email": "x@iso-demo.com"})
    assert made.status_code == 403

    FeatureService(w.db).set(w.a.rid, "reservations", None, w.boss)                    # back on
    assert book(w, w.a.restaurant).status_code == 200


def test_a_flag_check_never_leaks_to_people_without_access(world):
    w = world
    FeatureService(w.db).set(w.a.rid, "reservations", False, w.boss)
    r = w.client.get(f"{API}/admin/reservations", params={"restaurant_id": w.a.rid}, headers=header(w.b.admin))
    assert r.status_code == 403 and "restaurant" in r.json()["detail"].lower()          # access error, not "feature off"


def test_the_site_learns_its_flags_from_the_tenant_endpoint(world, monkeypatch):
    w = world
    FeatureService(w.db).set(w.a.rid, "custom_branding", True, w.boss)
    monkeypatch.setattr(settings, "PLATFORM_DOMAIN", "dineflow.test")
    monkeypatch.setattr(settings, "DEFAULT_TENANT_SLUG", "")
    a = w.client.get(f"{API}/tenant", params={"host": f"{w.a.slug}.dineflow.test"}).json()
    b = w.client.get(f"{API}/tenant", params={"host": f"{w.b.slug}.dineflow.test"}).json()
    assert a["features"]["custom_branding"] is True and b["features"]["custom_branding"] is False
    assert set(a["features"]) == catalog_keys(w)


# ------------------------------------------------------------------ operator CLI

def test_cli_shows_sets_and_audits(world, monkeypatch, capsys):
    w = world
    monkeypatch.setattr(cli, "SessionLocal", lambda: _Ctx(w.db))
    assert cli.main(["features", w.a.slug, "kitchen_v2", "on"]) == 0
    out = capsys.readouterr().out
    assert "on   kitchen_v2" in out and "(override)" in out
    assert cli.main(["audit", w.a.slug]) == 0
    assert "cli" in capsys.readouterr().out
    assert cli.main(["features", w.a.slug, "kitchen_v2", "sideways"]) == 2
    assert w.db.query(AuditLog).filter(AuditLog.actor_label == "cli").count() == 1


class _Ctx:
    """Lets the CLI use the test's transaction (its own commit()s become savepoints there)."""
    def __init__(self, db): self.db = db
    def __enter__(self): return self.db
    def __exit__(self, *a): return False


# ------------------------------------------------------------------ the catalog itself: create/delete

def test_a_platform_admin_can_create_and_delete_a_flag(world):
    w, c, h = world, world.client, header(world.boss)
    created = c.post(feature_url(), headers=h, json={"key": "table_qr_art", "description": "Fancy QR code art", "default": True})
    assert created.status_code == 201, created.text
    assert created.json() == {"key": "table_qr_art", "description": "Fancy QR code art", "default": True}

    listing = c.get(feature_url(), headers=h).json()
    assert any(f["key"] == "table_qr_art" for f in listing)
    assert FeatureService(w.db).resolve(w.a.rid)["table_qr_art"] is True          # follows its own default already

    deleted = c.delete(feature_url("table_qr_art"), headers=h)
    assert deleted.status_code == 204
    assert "table_qr_art" not in catalog_keys(w)


def test_creating_a_flag_rejects_a_bad_key_or_a_duplicate(world):
    w, c, h = world, world.client, header(world.boss)
    for bad in ("Has-Caps", "1starts_with_digit", "has space", ""):
        r = c.post(feature_url(), headers=h, json={"key": bad, "description": "x", "default": False})
        assert r.status_code == 422, bad

    dupe = c.post(feature_url(), headers=h, json={"key": "reservations", "description": "already exists", "default": False})
    assert dupe.status_code == 409


def test_deleting_a_flag_takes_its_overrides_with_it(world):
    w, c, h = world, world.client, header(world.boss)
    c.post(feature_url(), headers=h, json={"key": "throwaway", "description": "temp", "default": False})
    c.put(flag_url(w.a.rid, "throwaway"), headers=h, json={"enabled": True})
    assert FeatureService(w.db).resolve(w.a.rid)["throwaway"] is True

    assert c.delete(feature_url("throwaway"), headers=h).status_code == 204
    from app.models.feature_override import FeatureOverride
    assert w.db.query(FeatureOverride).filter_by(key="throwaway").count() == 0
    assert "throwaway" not in FeatureService(w.db).resolve(w.a.rid)


def test_a_newly_created_flag_does_nothing_until_code_checks_it(world):
    """The whole point of a DB-only flag: creating it from the UI alone never gates anything by itself."""
    w, c, h = world, world.client, header(world.boss)
    c.post(feature_url(), headers=h, json={"key": "unwired", "description": "nothing checks this", "default": False})
    c.put(flag_url(w.a.rid, "unwired"), headers=h, json={"enabled": True})
    # Turning it on changes nothing observable anywhere else — there's simply no route or page gated on it.
    assert book(w, w.a.restaurant).status_code == 200


def test_only_a_platform_admin_manages_the_catalog(world):
    w, c = world, world.client
    for who in (None, w.a.customer, w.a.staff, w.a.admin):
        h = header(who) if who else {}
        expected = 401 if who is None else 403
        assert c.get(feature_url(), headers=h).status_code == expected
        assert c.post(feature_url(), headers=h, json={"key": "nope", "description": "x", "default": False}).status_code == expected
        assert c.delete(feature_url("kitchen_v2"), headers=h).status_code == expected
    assert "kitchen_v2" in catalog_keys(w)  # the delete attempts above never actually went through


def test_deleting_an_unknown_flag_is_a_404(world):
    r = world.client.delete(feature_url("no-such-flag"), headers=header(world.boss))
    assert r.status_code == 404
