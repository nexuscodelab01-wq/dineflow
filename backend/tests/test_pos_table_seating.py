"""Staff seat a walk-in table directly from the POS — no QR scan needed. Idempotent like the guest-QR
path's own _open_session (tapping "Seat" twice on the same table returns the same session)."""

import pytest

from app.db.session import get_db
from app.main import app
from app.models.enums import TableStatus
from app.models.restaurant_user import RestaurantUser
from app.models.table_session import TableSession
from app.services.feature_service import FeatureService
from tests.conftest import override_get_db
from tests.tenants import header, make_tenant

API = "/api/v1"


@pytest.fixture
def world(client, db):
    app.dependency_overrides[get_db] = override_get_db(db)
    a = make_tenant(db, "Alpha")
    FeatureService(db).set(a.rid, "pos", True, None, actor_label="test")
    FeatureService(db).set(a.rid, "qr_table_ordering", True, None, actor_label="test")  # place_round itself still gates on this
    yield type("W", (), {"client": client, "db": db, "a": a})
    app.dependency_overrides.clear()


def membership_id(w, tenant, user):
    return w.db.query(RestaurantUser).filter_by(restaurant_id=tenant.rid, user_id=user.id).one().id


def pos_session(w, tenant, user, pin="1234"):
    """Returns (device_headers, staff_headers) — some POS routes (e.g. GET /pos/tables) are device-only."""
    mid = membership_id(w, tenant, user)
    r = w.client.post(f"{API}/admin/devices/staff/{mid}/pin", params={"restaurant_id": tenant.rid}, headers=header(tenant.admin), json={"pin": pin})
    assert r.status_code == 204
    paired = w.client.post(f"{API}/admin/devices", params={"restaurant_id": tenant.rid}, headers=header(tenant.admin), json={"label": "Till"})
    device_token = paired.json()["device_token"]
    login = w.client.post(f"{API}/pos/auth/pin-login", headers={"Authorization": f"Bearer {device_token}"}, json={"pin": pin})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {device_token}"}, {"Authorization": f"Bearer {login.json()['pos_session_token']}"}


def test_staff_can_list_tables(world):
    w = world
    device_headers, _ = pos_session(w, w.a, w.a.staff)
    r = w.client.get(f"{API}/pos/tables", headers=device_headers)
    assert r.status_code == 200, r.text
    tables = r.json()
    assert len(tables) == 1
    assert tables[0]["table_id"] == w.a.table.id


def test_seating_a_walk_in_opens_a_session_with_the_given_party_size(world):
    w = world
    _, staff_headers = pos_session(w, w.a, w.a.staff)

    r = w.client.post(f"{API}/pos/tables/{w.a.table.id}/seat", headers=staff_headers, json={"party_size": 4})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["table_id"] == w.a.table.id
    assert body["guests"] == 4
    assert body["rounds"] == 0

    session = w.db.query(TableSession).filter_by(table_id=w.a.table.id).one()
    assert session.party_size == 4
    assert w.db.get(type(w.a.table), w.a.table.id).status == TableStatus.OCCUPIED


def test_seating_an_already_open_table_is_idempotent(world):
    w = world
    _, staff_headers = pos_session(w, w.a, w.a.staff)

    first = w.client.post(f"{API}/pos/tables/{w.a.table.id}/seat", headers=staff_headers, json={"party_size": 2})
    second = w.client.post(f"{API}/pos/tables/{w.a.table.id}/seat", headers=staff_headers, json={"party_size": 6})
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["session_id"] == second.json()["session_id"]
    # The second call's party_size does not overwrite the first's — matches _open_session's own
    # "first one in wins" reuse semantics.
    assert second.json()["guests"] == 2


def test_seating_a_table_from_another_restaurant_is_404(world, db):
    w = world
    b = make_tenant(db, "Bravo")
    FeatureService(db).set(b.rid, "pos", True, None, actor_label="test")
    _, staff_headers_b = pos_session(type("X", (), {"client": w.client, "db": db}), b, b.staff)

    r = w.client.post(f"{API}/pos/tables/{w.a.table.id}/seat", headers=staff_headers_b, json={"party_size": 2})
    assert r.status_code == 404


def test_seating_requires_the_pos_flag(world):
    w = world
    _, staff_headers = pos_session(w, w.a, w.a.staff)
    FeatureService(w.db).set(w.a.rid, "pos", None, None, actor_label="test")  # back to default (off)

    r = w.client.post(f"{API}/pos/tables/{w.a.table.id}/seat", headers=staff_headers, json={"party_size": 2})
    assert r.status_code == 403


def test_a_round_can_be_sent_to_a_staff_seated_table(world):
    w = world
    _, staff_headers = pos_session(w, w.a, w.a.staff)
    seated = w.client.post(f"{API}/pos/tables/{w.a.table.id}/seat", headers=staff_headers, json={"party_size": 3})
    session_id = seated.json()["session_id"]

    r = w.client.post(
        f"{API}/pos/table-sessions/{session_id}/orders", headers=staff_headers,
        json={"items": [{"menu_item_id": w.a.item.id, "quantity": 1, "modifier_option_ids": []}]},
    )
    assert r.status_code == 200, r.text
