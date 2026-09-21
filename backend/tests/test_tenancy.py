"""Tenant identity: per-restaurant customers, bound tokens, host resolution, order numbers."""

import pytest

from app.core import tenancy
from app.core.config import settings
from app.db.session import get_db
from app.main import app
from app.models.enums import RoleName
from tests.conftest import override_get_db
from tests.tenants import make_tenant, make_user, place_order

API = "/api/v1"
PASSWORD = "Sturdy-Pass9"


@pytest.fixture
def two(client, db):
    app.dependency_overrides[get_db] = override_get_db(db)
    yield type("Two", (), {"client": client, "db": db, "a": make_tenant(db, "Alpha"), "b": make_tenant(db, "Bravo")})
    app.dependency_overrides.clear()


def register(client, rid, email="shared@iso-demo.com"):
    return client.post(f"{API}/auth/register", json={
        "restaurant_id": rid, "email": email, "password": PASSWORD, "first_name": "S", "last_name": "H"})


# ------------------------------------------------------------------ customers belong to one restaurant

def test_the_same_email_can_be_a_customer_of_two_restaurants(two):
    assert register(two.client, two.a.rid).status_code == 201
    assert register(two.client, two.b.rid).status_code == 201           # separate account, same email
    assert register(two.client, two.a.rid).status_code == 409           # but not twice at one restaurant


def test_login_only_finds_the_customer_of_that_restaurant(two):
    c = two.client
    register(c, two.a.rid)
    body = {"email": "shared@iso-demo.com", "password": PASSWORD}
    assert c.post(f"{API}/auth/login", json={**body, "restaurant_id": two.a.rid}).status_code == 200
    assert c.post(f"{API}/auth/login", json={**body, "restaurant_id": two.b.rid}).status_code == 401
    assert c.post(f"{API}/auth/login", json=body).status_code == 401    # no restaurant: global identities only


def test_registering_at_an_unknown_or_inactive_restaurant_is_refused(two):
    assert register(two.client, 999999).status_code == 404
    two.a.restaurant.is_active = False
    two.db.flush()
    assert register(two.client, two.a.rid).status_code == 404


def test_staff_sign_in_without_a_restaurant_and_get_a_null_tenant(two):
    r = two.client.post(f"{API}/auth/login", json={"email": two.a.admin.email, "password": "Test1234!"})
    assert r.status_code == 200
    me = two.client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"})
    assert me.status_code == 200 and me.json()["restaurant_id"] is None


def test_refreshing_keeps_the_token_bound_to_the_tenant(two):
    tokens = register(two.client, two.b.rid).json()
    fresh = two.client.post(f"{API}/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).json()
    me = two.client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {fresh['access_token']}"}).json()
    assert me["restaurant_id"] == two.b.rid


def test_my_restaurants_lists_only_what_the_account_may_manage(two):
    from tests.tenants import header
    c = two.client
    assert [r["id"] for r in c.get(f"{API}/auth/my-restaurants", headers=header(two.a.admin)).json()] == [two.a.rid]
    assert c.get(f"{API}/auth/my-restaurants", headers=header(two.a.customer)).json() == []
    boss = make_user(two.db, "boss@iso-demo.com", RoleName.SUPER_ADMIN)
    ids = {r["id"] for r in c.get(f"{API}/auth/my-restaurants", headers=header(boss)).json()}
    assert {two.a.rid, two.b.rid} <= ids


# ------------------------------------------------------------------ order numbers

def test_order_numbers_count_up_per_restaurant_with_its_own_prefix(two):
    nums = lambda t: [place_order(two.client, t).json()["order_number"] for _ in range(3)]
    assert nums(two.a) == ["AL-1001", "AL-1002", "AL-1003"]
    assert nums(two.b) == ["BR-1001", "BR-1002", "BR-1003"]


# ------------------------------------------------------------------ host -> restaurant

@pytest.fixture
def platform(monkeypatch):
    monkeypatch.setattr(settings, "PLATFORM_DOMAIN", "dineflow.app")
    monkeypatch.setattr(settings, "DEFAULT_TENANT_SLUG", "")


@pytest.mark.parametrize("host,slug", [
    ("alpha-kitchen.dineflow.app", "alpha-kitchen"),
    ("ALPHA-KITCHEN.dineflow.app:443", "alpha-kitchen"),
    ("alpha-kitchen.dineflow.app.", "alpha-kitchen"),
    ("dineflow.app", None), ("www.dineflow.app", None), ("a.b.dineflow.app", None),
    ("alpha-kitchen.evil.com", None), ("xdineflow.app", None), ("-bad.dineflow.app", None),
])
def test_slug_from_host(platform, host, slug):
    assert tenancy.slug_from_host(host) == slug


def test_tenant_endpoint_resolves_subdomains_custom_domains_and_the_default(two, platform, monkeypatch):
    c = two.client
    got = lambda host: c.get(f"{API}/tenant", params={"host": host})
    assert got("alpha-kitchen.dineflow.app").json()["id"] == two.a.rid
    assert got("nobody.dineflow.app").status_code == 404

    two.b.restaurant.custom_domain = "order.bravo.example"
    two.db.flush()
    assert got("Order.Bravo.example:8080").json()["id"] == two.b.rid

    assert got("dineflow.app").status_code == 404                        # no default configured
    monkeypatch.setattr(settings, "DEFAULT_TENANT_SLUG", "alpha-kitchen")
    assert got("dineflow.app").json()["id"] == two.a.rid                 # bare host falls back
    assert got("nobody.dineflow.app").status_code == 404                 # an unclaimed subdomain never does

    two.a.restaurant.is_active = False
    two.db.flush()
    assert got("alpha-kitchen.dineflow.app").status_code == 404


def test_cors_allows_platform_subdomains_only(platform):
    import re
    assert tenancy.origin_regex() is not None
    rx = re.compile(tenancy.origin_regex())
    assert rx.match("https://alpha-kitchen.dineflow.app") and rx.match("http://dineflow.app:3000")
    assert not rx.match("https://dineflow.app.evil.com") and not rx.match("https://evildineflow.app")
