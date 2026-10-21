"""Device kinds: a TILL owns a cash drawer (shift + float), a HANDHELD is carried by a server and has none.
Existing devices default to TILL so nothing already paired changes behaviour."""

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


def pair(w, **body):
    return w.client.post(f"{API}/admin/devices", params={"restaurant_id": w.a.rid}, headers=header(w.a.admin), json={"label": "Till", **body})


def staff_session(w, device_token, pin="1234"):
    mid = w.db.query(RestaurantUser).filter_by(restaurant_id=w.a.rid, user_id=w.a.staff.id).one().id
    w.client.post(f"{API}/admin/devices/staff/{mid}/pin", params={"restaurant_id": w.a.rid}, headers=header(w.a.admin), json={"pin": pin})
    login = w.client.post(f"{API}/pos/auth/pin-login", headers={"Authorization": f"Bearer {device_token}"}, json={"pin": pin})
    assert login.status_code == 200, login.text
    return login.json()


def test_a_device_defaults_to_a_till(world):
    r = pair(world)
    assert r.status_code == 201, r.text
    assert r.json()["kind"] == "TILL"


def test_a_handheld_can_be_paired_and_is_listed_as_one(world):
    w = world
    r = pair(w, kind="HANDHELD", label="Server 1")
    assert r.status_code == 201, r.text
    assert r.json()["kind"] == "HANDHELD"
    listed = w.client.get(f"{API}/admin/devices", params={"restaurant_id": w.a.rid}, headers=header(w.a.admin)).json()
    assert [d["kind"] for d in listed] == ["HANDHELD"]


def test_an_unknown_kind_is_refused(world):
    assert pair(world, kind="TOASTER").status_code == 422


def test_pin_login_tells_the_app_what_kind_of_device_it_is(world):
    w = world
    till = staff_session(w, pair(w).json()["device_token"])
    handheld = staff_session(w, pair(w, kind="HANDHELD").json()["device_token"])
    assert till["device_kind"] == "TILL"
    assert handheld["device_kind"] == "HANDHELD"


def test_a_handheld_cannot_open_a_shift_but_a_till_can(world):
    w = world
    handheld = staff_session(w, pair(w, kind="HANDHELD").json()["device_token"])
    r = w.client.post(f"{API}/pos/shifts/open", headers={"Authorization": f"Bearer {handheld['pos_session_token']}"}, json={"starting_float": "50.00"})
    assert r.status_code == 400
    assert "no cash drawer" in r.json()["detail"]

    till = staff_session(w, pair(w).json()["device_token"], pin="5678")
    ok = w.client.post(f"{API}/pos/shifts/open", headers={"Authorization": f"Bearer {till['pos_session_token']}"}, json={"starting_float": "50.00"})
    assert ok.status_code == 201, ok.text


def test_a_handheld_can_still_take_and_settle_orders_with_no_shift(world):
    """The whole point: a server's iPad works without ever opening a till shift."""
    w = world
    handheld = staff_session(w, pair(w, kind="HANDHELD").json()["device_token"])
    headers = {"Authorization": f"Bearer {handheld['pos_session_token']}"}
    created = w.client.post(f"{API}/pos/orders", headers=headers, json={"items": [{"menu_item_id": w.a.item.id, "quantity": 1, "modifier_option_ids": []}]})
    assert created.status_code == 201, created.text
    paid = w.client.post(f"{API}/pos/orders/{created.json()['order_id']}/pay-cash", headers=headers)
    assert paid.status_code == 204, paid.text
