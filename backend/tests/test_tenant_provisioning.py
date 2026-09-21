"""create-tenant: a complete, isolated, branded restaurant from one command."""

import pytest

from app import cli
from app.core import storage
from app.core.exceptions import AppError, ConflictError
from app.core.security import verify_password
from app.core.storage import LocalStorage
from app.db.session import get_db
from app.main import app
from app.models.audit_log import AuditLog
from app.models.category import Category
from app.models.menu_item import MenuItem
from app.models.restaurant_table import RestaurantTable
from app.models.restaurant import Restaurant
from app.models.restaurant_user import RestaurantUser
from app.models.user import User
from app.services.feature_service import FeatureService
from app.services.tenant_provisioning import TEMPLATES, order_prefix, provision_tenant
from tests.conftest import override_get_db
from tests.tenants import header, make_tenant
from tests.test_storage import HAS_PILLOW, tiny_png

API = "/api/v1"


@pytest.fixture(autouse=True)
def tmp_storage(tmp_path):
    storage.set_storage(LocalStorage(tmp_path, "/uploads"))
    yield tmp_path
    storage.set_storage(None)


def create(db, **kw):
    args = dict(name="Luigi's Trattoria", slug="luigis", owner_email="owner@luigis-demo.com", color="#C0392B", template="pizzeria")
    return provision_tenant(db, **{**args, **kw})


def test_creates_a_complete_restaurant(db):
    r = create(db, owner_name="Luigi Rossi")
    rest = db.get(Restaurant, r.restaurant_id)
    owner = db.get(User, db.query(RestaurantUser).filter_by(restaurant_id=rest.id).one().user_id)
    assert (rest.slug, rest.order_prefix, rest.primary_color) == ("luigis", "LT", "#c0392b")
    assert db.query(Category).filter_by(restaurant_id=rest.id).count() == len(TEMPLATES["pizzeria"])
    assert db.query(MenuItem).filter_by(restaurant_id=rest.id).count() == sum(len(v) for v in TEMPLATES["pizzeria"].values())
    assert db.query(RestaurantTable).filter_by(restaurant_id=rest.id).count() >= 5
    assert FeatureService(db).resolve(rest.id)["custom_branding"] is True

    assert (owner.first_name, owner.last_name, owner.restaurant_id) == ("Luigi", "Rossi", None)
    assert r.owner_password and verify_password(r.owner_password, owner.hashed_password)
    assert db.query(AuditLog).filter_by(restaurant_id=rest.id, action="tenant.create").count() == 1


def test_the_new_owner_can_sign_in_and_only_reach_their_own_restaurant(db, client):
    app.dependency_overrides[get_db] = override_get_db(db)
    try:
        other = make_tenant(db, "Alpha")
        r = create(db)
        login = client.post(f"{API}/auth/login", json={"email": r.owner_email, "password": r.owner_password})
        assert login.status_code == 200
        h = {"Authorization": f"Bearer {login.json()['access_token']}"}
        assert client.get(f"{API}/admin/menu", params={"restaurant_id": r.restaurant_id}, headers=h).status_code == 200
        assert client.get(f"{API}/admin/menu", params={"restaurant_id": other.rid}, headers=h).status_code == 403
        assert [x["slug"] for x in client.get(f"{API}/auth/my-restaurants", headers=h).json()] == ["luigis"]
    finally:
        app.dependency_overrides.clear()


def test_an_existing_admin_can_own_several_restaurants(db):
    first = create(db)
    second = create(db, name="Second Place", slug="second-place", owner_email=first.owner_email)
    assert second.owner_email == first.owner_email and second.owner_password is None
    owner = db.query(User).filter_by(email=first.owner_email).one()
    assert db.query(RestaurantUser).filter_by(user_id=owner.id).count() == 2


@pytest.mark.parametrize("kw,message", [
    (dict(slug="Bad Slug"), "Slug"), (dict(slug="www"), "Slug"), (dict(slug="-x"), "Slug"),
    (dict(color="red"), "Colour"), (dict(color="#12345"), "Colour"), (dict(template="nope"), "Unknown template"),
    (dict(name="  "), "name"), (dict(logo=b"definitely not an image"), "Logo"),
])
def test_bad_input_is_refused_and_nothing_is_created(db, kw, message):
    with pytest.raises(AppError, match=message):
        create(db, **kw)
    assert db.query(Restaurant).filter_by(slug="luigis").count() == 0


def test_duplicate_slugs_are_refused(db):
    create(db)
    with pytest.raises(ConflictError):
        create(db, owner_email="someone@else-demo.com")


@pytest.mark.skipif(not HAS_PILLOW, reason="logo processing needs Pillow")
def test_the_logo_is_processed_and_stored_under_the_new_tenant(db, tmp_storage):
    rest = db.get(Restaurant, create(db, logo=tiny_png()).restaurant_id)
    assert rest.logo_url.startswith(f"/uploads/tenants/{rest.id}/branding/") and rest.logo_url.endswith(".webp")
    assert (tmp_storage / rest.logo_url.removeprefix("/uploads/")).exists()


def test_branding_can_be_left_off(db):
    rest_id = create(db, branding=False).restaurant_id
    assert FeatureService(db).resolve(rest_id)["custom_branding"] is False


def test_order_prefix_from_the_name():
    assert order_prefix("Bella Vista Kitchen") == "BVK"
    assert order_prefix("Luigi's Trattoria") == "LT"
    assert order_prefix("Nobu") == "NOB"
    assert order_prefix("!!") == "DF"


# ---------------------------------------------------------------- brand colour through the settings API

def test_admins_can_set_a_valid_brand_colour_only(db, client):
    app.dependency_overrides[get_db] = override_get_db(db)
    try:
        t = make_tenant(db, "Alpha")
        url = f"{API}/admin/settings"
        ok = client.patch(url, params={"restaurant_id": t.rid}, headers=header(t.admin), json={"primary_color": "#1E88E5"})
        assert ok.status_code == 200 and ok.json()["primary_color"] == "#1e88e5"
        for bad in ("blue", "#12", "#1e88e5;}body{display:none", "url(x)"):
            r = client.patch(url, params={"restaurant_id": t.rid}, headers=header(t.admin), json={"primary_color": bad})
            assert r.status_code == 422, bad
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------- the command

def test_cli_creates_a_tenant_and_prints_the_login(db, monkeypatch, capsys):
    class Ctx:
        def __enter__(self): return db
        def __exit__(self, *a): return False
    monkeypatch.setattr(cli, "SessionLocal", lambda: Ctx())
    assert cli.main(["create-tenant", "--name", "Cli Cafe", "--slug", "cli-cafe", "--owner", "boss@cli-cafe-demo.com",
                     "--color", "#2c6f53", "--template", "cafe"]) == 0
    out = capsys.readouterr().out
    assert "Created 'Cli Cafe'" in out and "boss@cli-cafe-demo.com /" in out
    with pytest.raises(SystemExit, match="already exists"):
        cli.main(["create-tenant", "--name", "Again", "--slug", "cli-cafe", "--owner", "x@cli-cafe-demo.com"])
