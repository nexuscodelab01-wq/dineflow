"""Clock in/out — one open time entry per person (not per device: unlike a till shift, an employee's
hours are about them, not which iPad they used)."""

import pytest

from app.db.session import get_db
from app.main import app
from app.models.restaurant_user import RestaurantUser
from app.services.feature_service import FeatureService
from tests.conftest import override_get_db
from tests.tenants import header, make_tenant

API = "/api/v1"


@pytest.fixture
def world(client, db):
    app.dependency_overrides[get_db] = override_get_db(db)
    a = make_tenant(db, "Alpha")
    FeatureService(db).set(a.rid, "pos", True, None, actor_label="test")
    yield type("W", (), {"client": client, "db": db, "a": a})
    app.dependency_overrides.clear()


def membership_id(w, tenant, user):
    return w.db.query(RestaurantUser).filter_by(restaurant_id=tenant.rid, user_id=user.id).one().id


def pos_session(w, tenant, user, pin="1234"):
    mid = membership_id(w, tenant, user)
    r = w.client.post(f"{API}/admin/devices/staff/{mid}/pin", params={"restaurant_id": tenant.rid}, headers=header(tenant.admin), json={"pin": pin})
    assert r.status_code == 204
    paired = w.client.post(f"{API}/admin/devices", params={"restaurant_id": tenant.rid}, headers=header(tenant.admin), json={"label": "Till"})
    device_token = paired.json()["device_token"]
    login = w.client.post(f"{API}/pos/auth/pin-login", headers={"Authorization": f"Bearer {device_token}"}, json={"pin": pin})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['pos_session_token']}"}


def test_current_entry_is_null_before_clocking_in(world):
    w = world
    staff_headers = pos_session(w, w.a, w.a.staff)

    r = w.client.get(f"{API}/pos/time-entries/current", headers=staff_headers)
    assert r.status_code == 200
    assert r.json() is None


def test_clock_in_then_clock_out(world):
    w = world
    staff_headers = pos_session(w, w.a, w.a.staff)

    clocked_in = w.client.post(f"{API}/pos/time-entries/clock-in", headers=staff_headers)
    assert clocked_in.status_code == 201, clocked_in.text
    assert clocked_in.json()["clock_out_at"] is None

    current = w.client.get(f"{API}/pos/time-entries/current", headers=staff_headers)
    assert current.status_code == 200
    assert current.json()["id"] == clocked_in.json()["id"]

    clocked_out = w.client.post(f"{API}/pos/time-entries/clock-out", headers=staff_headers)
    assert clocked_out.status_code == 200, clocked_out.text
    assert clocked_out.json()["id"] == clocked_in.json()["id"]
    assert clocked_out.json()["clock_out_at"] is not None

    current = w.client.get(f"{API}/pos/time-entries/current", headers=staff_headers)
    assert current.json() is None


def test_cannot_clock_in_twice(world):
    w = world
    staff_headers = pos_session(w, w.a, w.a.staff)
    w.client.post(f"{API}/pos/time-entries/clock-in", headers=staff_headers)

    r = w.client.post(f"{API}/pos/time-entries/clock-in", headers=staff_headers)
    assert r.status_code == 409


def test_cannot_clock_out_with_nothing_open(world):
    w = world
    staff_headers = pos_session(w, w.a, w.a.staff)

    r = w.client.post(f"{API}/pos/time-entries/clock-out", headers=staff_headers)
    assert r.status_code == 400


def test_clock_in_requires_the_pos_flag(world):
    w = world
    FeatureService(w.db).set(w.a.rid, "pos", None, None, actor_label="test")  # back to default (off)
    staff_headers = pos_session(w, w.a, w.a.staff)

    r = w.client.post(f"{API}/pos/time-entries/clock-in", headers=staff_headers)
    assert r.status_code == 403
