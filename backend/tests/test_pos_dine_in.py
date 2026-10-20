"""POS dine-in orders delegate straight to the existing waiter-view path (place_round) unchanged."""

import pytest

from app.db.session import get_db
from app.main import app
from app.models.enums import TableStatus
from app.models.order import Order
from app.models.restaurant_user import RestaurantUser
from app.models.table_session import OPEN, TableSession
from app.services.feature_service import FeatureService
from tests.conftest import override_get_db
from tests.tenants import header, make_tenant

API = "/api/v1"


@pytest.fixture
def world(client, db):
    app.dependency_overrides[get_db] = override_get_db(db)
    a = make_tenant(db, "Alpha")
    FeatureService(db).set(a.rid, "qr_table_ordering", True, None, actor_label="test")
    FeatureService(db).set(a.rid, "pos", True, None, actor_label="test")
    a.table.status = TableStatus.OCCUPIED
    db.flush()
    yield type("W", (), {"client": client, "db": db, "a": a})
    app.dependency_overrides.clear()


def open_session(w, t):
    r = w.client.post(f"{API}/t/{t.table.qr_token}/join", params={"restaurant_id": t.rid}, json={"name": "Guest"})
    assert r.status_code == 200, r.text
    return w.db.query(TableSession).filter_by(table_id=t.table.id, state=OPEN).one().id


def pos_session(w, tenant, user, pin="1234"):
    mid = w.db.query(RestaurantUser).filter_by(restaurant_id=tenant.rid, user_id=user.id).one().id
    w.client.post(f"{API}/admin/devices/staff/{mid}/pin", params={"restaurant_id": tenant.rid}, headers=header(tenant.admin), json={"pin": pin})
    device_token = w.client.post(f"{API}/admin/devices", params={"restaurant_id": tenant.rid}, headers=header(tenant.admin), json={"label": "Till"}).json()["device_token"]
    login = w.client.post(f"{API}/pos/auth/pin-login", headers={"Authorization": f"Bearer {device_token}"}, json={"pin": pin})
    return {"Authorization": f"Bearer {login.json()['pos_session_token']}"}


def test_a_pos_dine_in_round_lands_on_the_table_and_attributes_the_staff_member(world):
    w = world
    session_id = open_session(w, w.a)
    staff_headers = pos_session(w, w.a, w.a.staff)

    r = w.client.post(
        f"{API}/pos/table-sessions/{session_id}/orders", headers=staff_headers,
        json={"items": [{"menu_item_id": w.a.item.id, "quantity": 1, "modifier_option_ids": []}]},
    )
    assert r.status_code == 200, r.text
    order = w.db.query(Order).filter_by(table_session_id=session_id).one()
    assert order.customer_name == "Alpha (staff)"
    assert order.user_id == w.a.staff.id


def test_open_table_sessions_are_listed_for_the_pos(world):
    w = world
    open_session(w, w.a)
    device_token = w.client.post(f"{API}/admin/devices", params={"restaurant_id": w.a.rid}, headers=header(w.a.admin), json={"label": "Till"}).json()["device_token"]

    r = w.client.get(f"{API}/pos/table-sessions/open", headers={"Authorization": f"Bearer {device_token}"})
    assert r.status_code == 200
    assert len(r.json()["sessions"]) == 1


def test_a_pos_order_on_another_restaurants_session_is_refused(world, db):
    from tests.tenants import make_tenant as _mt

    w = world
    b = _mt(db, "Bravo")
    FeatureService(db).set(b.rid, "pos", True, None, actor_label="test")
    session_id = open_session(w, w.a)
    staff_headers_b = pos_session(type("X", (), {"client": w.client, "db": db}), b, b.staff)

    r = w.client.post(
        f"{API}/pos/table-sessions/{session_id}/orders", headers=staff_headers_b,
        json={"items": [{"menu_item_id": w.a.item.id, "quantity": 1, "modifier_option_ids": []}]},
    )
    assert r.status_code == 404
