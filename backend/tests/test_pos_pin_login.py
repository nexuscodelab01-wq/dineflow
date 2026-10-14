"""PIN quick-switch: correct/wrong PIN, inactive/cross-tenant rejection, revoked device."""

import pytest

from app.db.session import get_db
from app.main import app
from app.models.restaurant_user import RestaurantUser
from tests.conftest import override_get_db
from tests.tenants import header, make_tenant

API = "/api/v1"


@pytest.fixture
def world(client, db):
    app.dependency_overrides[get_db] = override_get_db(db)
    yield type("W", (), {"client": client, "db": db, "a": make_tenant(db, "Alpha"), "b": make_tenant(db, "Bravo")})
    app.dependency_overrides.clear()


def pair(w, tenant):
    r = w.client.post(f"{API}/admin/devices", params={"restaurant_id": tenant.rid}, headers=header(tenant.admin), json={"label": "Till"})
    assert r.status_code == 201
    return r.json()["device_token"], r.json()["device_id"]


def membership_id(w, tenant, user):
    return w.db.query(RestaurantUser).filter_by(restaurant_id=tenant.rid, user_id=user.id).one().id


def set_pin(w, tenant, user, pin):
    mid = membership_id(w, tenant, user)
    r = w.client.post(f"{API}/admin/devices/staff/{mid}/pin", params={"restaurant_id": tenant.rid}, headers=header(tenant.admin), json={"pin": pin})
    assert r.status_code == 204, r.text


def test_correct_pin_logs_in(world):
    w = world
    set_pin(w, w.a, w.a.staff, "1234")
    device_token, _ = pair(w, w.a)

    r = w.client.post(f"{API}/pos/auth/pin-login", headers={"Authorization": f"Bearer {device_token}"}, json={"pin": "1234"})
    assert r.status_code == 200, r.text
    assert r.json()["pos_session_token"] and r.json()["staff_name"] == "Alpha"


def test_wrong_pin_is_refused(world):
    w = world
    set_pin(w, w.a, w.a.staff, "1234")
    device_token, _ = pair(w, w.a)

    r = w.client.post(f"{API}/pos/auth/pin-login", headers={"Authorization": f"Bearer {device_token}"}, json={"pin": "9999"})
    assert r.status_code == 400


def test_pin_is_scoped_per_restaurant(world):
    """The same digits mean nothing across tenants: B's staff can freely reuse A's PIN, and logging in
    at B's own device with it resolves to B's own staff member, never A's."""
    w = world
    set_pin(w, w.a, w.a.staff, "1234")
    set_pin(w, w.b, w.b.staff, "1234")  # no conflict — different restaurant
    device_token_b, _ = pair(w, w.b)

    r = w.client.post(f"{API}/pos/auth/pin-login", headers={"Authorization": f"Bearer {device_token_b}"}, json={"pin": "1234"})
    assert r.status_code == 200
    assert r.json()["staff_name"] == "Bravo"  # not Alpha's staff member


def test_a_device_pairing_doesnt_let_a_remote_restaurants_pin_log_in(world):
    w = world
    set_pin(w, w.a, w.a.staff, "9999")  # only A has this PIN
    device_token_b, _ = pair(w, w.b)

    r = w.client.post(f"{API}/pos/auth/pin-login", headers={"Authorization": f"Bearer {device_token_b}"}, json={"pin": "9999"})
    assert r.status_code == 400


def test_an_inactive_memberships_pin_is_refused(world):
    w = world
    set_pin(w, w.a, w.a.staff, "1234")
    membership = w.db.query(RestaurantUser).filter_by(restaurant_id=w.a.rid, user_id=w.a.staff.id).one()
    membership.is_active = False
    w.db.commit()
    device_token, _ = pair(w, w.a)

    r = w.client.post(f"{API}/pos/auth/pin-login", headers={"Authorization": f"Bearer {device_token}"}, json={"pin": "1234"})
    assert r.status_code == 400


def test_a_revoked_device_refuses_pin_login(world):
    w = world
    set_pin(w, w.a, w.a.staff, "1234")
    device_token, device_id = pair(w, w.a)
    w.client.post(f"{API}/admin/devices/{device_id}/revoke", params={"restaurant_id": w.a.rid}, headers=header(w.a.admin))

    r = w.client.post(f"{API}/pos/auth/pin-login", headers={"Authorization": f"Bearer {device_token}"}, json={"pin": "1234"})
    assert r.status_code == 401


def test_two_staff_at_one_restaurant_cannot_share_a_pin(world):
    w = world
    set_pin(w, w.a, w.a.staff, "1234")
    mid = membership_id(w, w.a, w.a.admin)
    r = w.client.post(f"{API}/admin/devices/staff/{mid}/pin", params={"restaurant_id": w.a.rid}, headers=header(w.a.admin), json={"pin": "1234"})
    assert r.status_code == 409
