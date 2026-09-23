"""Platform console: creating a restaurant over the API, and custom domains (mocked verification)."""

import pytest

from app.db.session import get_db
from app.main import app
from app.models.audit_log import AuditLog
from app.models.enums import RoleName
from app.models.restaurant import Restaurant
from tests.conftest import override_get_db
from tests.tenants import header, make_tenant, make_user

API = "/api/v1"


@pytest.fixture
def world(client, db):
    app.dependency_overrides[get_db] = override_get_db(db)
    boss = make_user(db, "boss@iso-demo.com", RoleName.SUPER_ADMIN)
    yield type("W", (), {"client": client, "db": db, "a": make_tenant(db, "Alpha"), "b": make_tenant(db, "Bravo"), "boss": boss})
    app.dependency_overrides.clear()


def create(w, who=None, **fields):
    data = {"name": "Onboard Kitchen", "slug": "onboard-kitchen", "owner_email": "onboard-owner@iso-demo.com", **fields}
    return w.client.post(f"{API}/platform/restaurants", headers=header(who or w.boss), data=data)


# ------------------------------------------------------------------ creating a restaurant

def test_a_platform_admin_can_create_a_restaurant(world):
    w = world
    r = create(w, color="#2c6f53", secondary_color="#f1c40f", template="cafe", timezone="America/Los_Angeles")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["slug"] == "onboard-kitchen" and body["owner_email"] == "onboard-owner@iso-demo.com"
    assert body["invite_link"] and "/reset-password?token=" in body["invite_link"]
    assert body["site_url"]

    restaurant = w.db.query(Restaurant).filter_by(slug="onboard-kitchen").one()
    assert restaurant.timezone == "America/Los_Angeles" and restaurant.primary_color == "#2c6f53"
    assert restaurant.secondary_color == "#f1c40f"
    assert w.db.query(AuditLog).filter_by(restaurant_id=restaurant.id, action="tenant.create").count() == 1


def test_a_restaurant_can_be_created_without_a_secondary_colour(world):
    w = world
    r = create(w, color="#2c6f53")
    assert r.status_code == 201, r.text
    restaurant = w.db.query(Restaurant).filter_by(slug="onboard-kitchen").one()
    assert restaurant.secondary_color is None


def test_only_a_platform_admin_can_create_a_restaurant(world):
    w = world
    for who, expect in ((None, 401), (w.a.customer, 403), (w.a.admin, 403), (w.a.staff, 403)):
        h = header(who) if who else {}
        r = w.client.post(f"{API}/platform/restaurants", headers=h, data={"name": "X", "slug": "x-kitchen", "owner_email": "x@iso-demo.com"})
        assert r.status_code == expect
    assert w.db.query(Restaurant).filter_by(slug="x-kitchen").count() == 0


def test_bad_input_creates_nothing(world):
    w = world
    assert create(w, slug="Not A Slug").status_code == 400
    assert create(w, color="not-a-color").status_code == 400
    assert create(w, secondary_color="not-a-color").status_code == 400
    assert create(w, timezone="Nowhere/Nothing").status_code == 400
    assert w.db.query(Restaurant).filter_by(slug="onboard-kitchen").count() == 0


def test_a_duplicate_slug_is_refused(world):
    w = world
    assert create(w).status_code == 201
    again = create(w, owner_email="someone-else@iso-demo.com")
    assert again.status_code == 409


def test_the_template_list_is_available(world):
    r = world.client.get(f"{API}/platform/restaurants/templates", headers=header(world.boss))
    assert r.status_code == 200 and "generic" in r.json()


# ------------------------------------------------------------------ custom domains

def test_setting_a_custom_domain_from_settings(world):
    w = world
    ok = w.client.patch(f"{API}/admin/settings", params={"restaurant_id": w.a.rid}, headers=header(w.a.admin), json={"custom_domain": "Order.Alpha-Kitchen.com"})
    assert ok.status_code == 200
    body = ok.json()
    assert body["custom_domain"] == "order.alpha-kitchen.com" and body["domain_verified_at"] is None  # lowercased


def test_bad_custom_domains_are_refused(world):
    w = world
    for bad in ("not a domain", "http://order.example.com", "onlyoneword", "-bad.example.com"):
        r = w.client.patch(f"{API}/admin/settings", params={"restaurant_id": w.a.rid}, headers=header(w.a.admin), json={"custom_domain": bad})
        assert r.status_code == 422, bad


def test_two_restaurants_cannot_share_a_custom_domain(world):
    w = world
    w.client.patch(f"{API}/admin/settings", params={"restaurant_id": w.a.rid}, headers=header(w.a.admin), json={"custom_domain": "order.shared.com"})
    clash = w.client.patch(f"{API}/admin/settings", params={"restaurant_id": w.b.rid}, headers=header(w.b.admin), json={"custom_domain": "order.shared.com"})
    assert clash.status_code == 409


def test_changing_the_domain_clears_verification_and_a_platform_admin_can_verify_it(world):
    w = world
    w.client.patch(f"{API}/admin/settings", params={"restaurant_id": w.a.rid}, headers=header(w.a.admin), json={"custom_domain": "order.alpha-kitchen.com"})

    verified = w.client.post(f"{API}/platform/restaurants/{w.a.rid}/verify-domain", headers=header(w.boss))
    assert verified.status_code == 200 and verified.json()["domain_verified_at"] is not None

    # changing the domain again clears the verification
    changed = w.client.patch(f"{API}/admin/settings", params={"restaurant_id": w.a.rid}, headers=header(w.a.admin), json={"custom_domain": "order2.alpha-kitchen.com"})
    assert changed.json()["domain_verified_at"] is None


def test_only_a_platform_admin_can_verify_a_domain(world):
    w = world
    w.client.patch(f"{API}/admin/settings", params={"restaurant_id": w.a.rid}, headers=header(w.a.admin), json={"custom_domain": "order.alpha-kitchen.com"})
    assert w.client.post(f"{API}/platform/restaurants/{w.a.rid}/verify-domain", headers=header(w.a.admin)).status_code == 403


def test_verifying_a_restaurant_with_no_domain_is_refused(world):
    r = world.client.post(f"{API}/platform/restaurants/{world.a.rid}/verify-domain", headers=header(world.boss))
    assert r.status_code == 400


# ------------------------------------------------------------------ branding colours (after creation)

def test_setting_colours_from_settings(world):
    w = world
    ok = w.client.patch(f"{API}/admin/settings", params={"restaurant_id": w.a.rid}, headers=header(w.a.admin), json={"primary_color": "#2C6F53", "secondary_color": "#F1C40F"})
    assert ok.status_code == 200
    body = ok.json()
    assert body["primary_color"] == "#2c6f53" and body["secondary_color"] == "#f1c40f"  # lowercased


def test_clearing_the_secondary_colour_with_an_empty_string(world):
    w = world
    w.client.patch(f"{API}/admin/settings", params={"restaurant_id": w.a.rid}, headers=header(w.a.admin), json={"secondary_color": "#f1c40f"})
    cleared = w.client.patch(f"{API}/admin/settings", params={"restaurant_id": w.a.rid}, headers=header(w.a.admin), json={"secondary_color": ""})
    assert cleared.status_code == 200 and cleared.json()["secondary_color"] is None


def test_bad_colours_are_refused(world):
    w = world
    for field in ("primary_color", "secondary_color"):
        r = w.client.patch(f"{API}/admin/settings", params={"restaurant_id": w.a.rid}, headers=header(w.a.admin), json={field: "not-a-color"})
        assert r.status_code == 422, field


# ------------------------------------------------------------------ home page content

def test_setting_home_page_content(world):
    w = world
    r = w.client.patch(f"{API}/admin/settings", params={"restaurant_id": w.a.rid}, headers=header(w.a.admin), json={
        "about_text": "We've been serving pasta since 1990.",
        "gallery": ["/uploads/tenants/1/gallery/a.webp", "https://example.com/photo.jpg"],
        "social_links": {"instagram": "https://instagram.com/alpha", "facebook": "https://facebook.com/alpha"},
        "latitude": "40.712800", "longitude": "-74.006000",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["about_text"] == "We've been serving pasta since 1990."
    assert body["gallery"] == ["/uploads/tenants/1/gallery/a.webp", "https://example.com/photo.jpg"]
    assert body["social_links"] == {"instagram": "https://instagram.com/alpha", "facebook": "https://facebook.com/alpha"}
    assert body["latitude"] == "40.712800" and body["longitude"] == "-74.006000"


def test_an_unknown_social_link_is_refused(world):
    w = world
    r = w.client.patch(f"{API}/admin/settings", params={"restaurant_id": w.a.rid}, headers=header(w.a.admin), json={
        "social_links": {"myspace": "https://myspace.com/alpha"},
    })
    assert r.status_code == 422


def test_a_social_link_must_be_a_full_url(world):
    w = world
    r = w.client.patch(f"{API}/admin/settings", params={"restaurant_id": w.a.rid}, headers=header(w.a.admin), json={
        "social_links": {"instagram": "alpha"},
    })
    assert r.status_code == 422


def test_a_gallery_image_must_be_uploaded_or_a_link(world):
    w = world
    r = w.client.patch(f"{API}/admin/settings", params={"restaurant_id": w.a.rid}, headers=header(w.a.admin), json={
        "gallery": ["not a url"],
    })
    assert r.status_code == 422


def test_too_many_gallery_images_is_refused(world):
    w = world
    r = w.client.patch(f"{API}/admin/settings", params={"restaurant_id": w.a.rid}, headers=header(w.a.admin), json={
        "gallery": [f"https://example.com/{i}.jpg" for i in range(21)],
    })
    assert r.status_code == 422


def test_bad_coordinates_are_refused(world):
    w = world
    for field, bad in (("latitude", "91"), ("latitude", "-91"), ("longitude", "181"), ("longitude", "-181")):
        r = w.client.patch(f"{API}/admin/settings", params={"restaurant_id": w.a.rid}, headers=header(w.a.admin), json={field: bad})
        assert r.status_code == 422, (field, bad)


def test_removing_a_gallery_image_deletes_the_stored_file(world):
    w = world
    w.client.patch(f"{API}/admin/settings", params={"restaurant_id": w.a.rid}, headers=header(w.a.admin), json={
        "gallery": [f"/uploads/tenants/{w.a.rid}/gallery/keep.webp", f"/uploads/tenants/{w.a.rid}/gallery/drop.webp"],
    })
    r = w.client.patch(f"{API}/admin/settings", params={"restaurant_id": w.a.rid}, headers=header(w.a.admin), json={
        "gallery": [f"/uploads/tenants/{w.a.rid}/gallery/keep.webp"],
    })
    assert r.status_code == 200 and r.json()["gallery"] == [f"/uploads/tenants/{w.a.rid}/gallery/keep.webp"]
