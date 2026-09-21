"""QR table ordering: scanning, the shared tab, rounds, seated-only policy, closing, and staying inside one restaurant."""

import pytest

from app.core.config import settings
from app.core.security import create_access_token
from app.db.session import get_db
from app.main import app
from app.models.enums import OrderStatus, RoleName, TableStatus
from app.models.order import Order
from app.models.table_session import OPEN, TableSession
from app.services.feature_service import FeatureService
from tests.conftest import override_get_db
from tests.tenants import header, make_tenant, make_user

API = "/api/v1"


@pytest.fixture
def world(client, db):
    app.dependency_overrides[get_db] = override_get_db(db)
    a, b = make_tenant(db, "Alpha"), make_tenant(db, "Bravo")
    boss = make_user(db, "boss@iso-demo.com", RoleName.SUPER_ADMIN)
    for t in (a, b):
        FeatureService(db).set(t.rid, "qr_table_ordering", True, boss)
        t.table.status = TableStatus.OCCUPIED       # seated
    db.flush()
    yield type("W", (), {"client": client, "db": db, "a": a, "b": b, "boss": boss})
    app.dependency_overrides.clear()


def info(w, t, **kw):
    return w.client.get(f"{API}/t/{t.table.qr_token}", params={"restaurant_id": t.rid, **kw})


def join(w, t, name=None):
    r = w.client.post(f"{API}/t/{t.table.qr_token}/join", params={"restaurant_id": t.rid}, json={"name": name})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def send(w, t, h, qty=1, key=None, item=None, **extra):
    headers = {**h, **({"Idempotency-Key": key} if key else {})}
    return w.client.post(f"{API}/table-session/orders", headers=headers, json={
        "items": [{"menu_item_id": (item or t.item).id, "quantity": qty, "modifier_option_ids": []}], **extra})


# ------------------------------------------------------------------ scanning

def test_scanning_shows_the_table_and_whether_ordering_is_open(world):
    w = world
    got = info(w, w.a).json()
    assert (got["restaurant_name"], got["table_number"], got["ordering_open"], got["reason"]) == ("Alpha Kitchen", "A1", True, None)
    w.a.table.status = TableStatus.AVAILABLE
    w.db.flush()
    closed = info(w, w.a).json()
    assert closed["ordering_open"] is False and "seated" in closed["reason"]
    assert w.client.post(f"{API}/t/{w.a.table.qr_token}/join", json={}).status_code == 403      # can't join a table nobody sits at
    w.a.restaurant.qr_access_policy = "OPEN"                                                     # the restaurant's own choice
    w.db.flush()
    assert info(w, w.a).json()["ordering_open"] is True


def test_the_feature_flag_switches_qr_ordering_off_per_restaurant(world):
    w = world
    FeatureService(w.db).set(w.a.rid, "qr_table_ordering", False, w.boss)
    assert info(w, w.a).status_code == 403
    assert w.client.post(f"{API}/t/{w.a.table.qr_token}/join", json={}).status_code == 403
    assert info(w, w.b).status_code == 200


def test_unknown_rotated_or_foreign_tokens_all_look_the_same(world):
    w = world
    assert w.client.get(f"{API}/t/not-a-real-token").status_code == 404
    assert w.client.get(f"{API}/t/{w.a.table.qr_token}", params={"restaurant_id": w.b.rid}).status_code == 404   # Alpha's QR on Bravo's site
    w.a.table.is_active = False
    w.db.flush()
    assert info(w, w.a).status_code == 404


# ------------------------------------------------------------------ the shared tab

def test_everyone_at_a_table_joins_one_session_and_sees_the_same_tab(world):
    w = world
    sam, kim = join(w, w.a, "Sam"), join(w, w.a, "Kim")
    assert w.db.query(TableSession).filter_by(table_id=w.a.table.id, state=OPEN).count() == 1
    assert send(w, w.a, sam, qty=2).status_code == 201
    assert send(w, w.a, kim).status_code == 201

    for who in (sam, kim):
        view = w.client.get(f"{API}/table-session", headers=who).json()
        assert view["table_number"] == "A1" and sorted(view["guests"]) == ["Kim", "Sam"]
        assert [(r["round_no"], r["ordered_by"], r["items"][0]["quantity"]) for r in view["rounds"]] == [(1, "Sam", 2), (2, "Kim", 1)]
        assert float(view["total"]) == pytest.approx(3 * 12.0 * 1.10)


def test_a_round_reaches_the_kitchen_as_a_table_order(world):
    w = world
    r = send(w, w.a, join(w, w.a, "Sam"), qty=2, notes="no ice")
    assert r.status_code == 201, r.text
    order = w.db.get(Order, r.json()["order_id"])
    assert (order.order_type.value, order.status, order.user_id, order.table_id, order.round_no) == ("DINE_IN", OrderStatus.CONFIRMED, None, w.a.table.id, 1)
    assert order.order_number.startswith("AL-") and order.customer_name == "Sam" and order.customer_email is None

    board = w.client.get(f"{API}/admin/kitchen", params={"restaurant_id": w.a.rid}, headers=header(w.a.staff)).json()
    seen = [o for col in board.values() for o in col if o["id"] == order.id]
    assert seen and seen[0]["table_number"] == "A1"


def test_sending_the_same_key_twice_makes_one_round(world):
    w = world
    h = join(w, w.a)
    first, again = send(w, w.a, h, key="tap-1"), send(w, w.a, h, key="tap-1")
    assert first.status_code == again.status_code == 201 and first.json()["order_id"] == again.json()["order_id"]
    assert send(w, w.a, h, key="tap-2").json()["round_no"] == 2
    assert w.db.query(Order).filter(Order.table_id == w.a.table.id).count() == 2


def test_bad_rounds_are_refused_and_leave_no_order(world, monkeypatch):
    w = world
    h = join(w, w.a)
    assert send(w, w.a, h, item=w.b.item).status_code == 400                       # another restaurant's dish
    w.a.item.is_available = False
    w.db.flush()
    assert send(w, w.a, h).status_code == 400                                       # sold out
    w.a.item.is_available = True
    monkeypatch.setattr(settings, "QR_MAX_ORDER_TOTAL", 20.0)
    too_big = send(w, w.a, h, qty=5)
    assert too_big.status_code == 400 and "too large" in too_big.json()["detail"]
    assert w.client.post(f"{API}/table-session/orders", headers=h, json={"items": []}).status_code == 422
    assert w.db.query(Order).filter(Order.table_id == w.a.table.id).count() == 0


# ------------------------------------------------------------------ passes are not logins

def test_a_table_pass_is_not_an_account_and_an_account_is_not_a_table_pass(world):
    w = world
    guest = join(w, w.a)
    assert w.client.get(f"{API}/auth/me", headers=guest).status_code == 401
    assert w.client.get(f"{API}/admin/menu", params={"restaurant_id": w.a.rid}, headers=guest).status_code == 401
    assert w.client.post(f"{API}/orders", headers=guest, json={}).status_code == 401
    assert w.client.get(f"{API}/table-session").status_code == 401
    for account in (header(w.a.customer), header(w.a.admin)):
        assert w.client.get(f"{API}/table-session", headers=account).status_code == 401
    forged = {"Authorization": "Bearer " + create_access_token("1", claims={"type": "guest", "sess": 1, "tenant": w.a.rid})}
    assert w.client.get(f"{API}/table-session", headers=forged).status_code == 401       # wrong signature type/claims


def test_a_pass_only_reaches_its_own_table(world):
    w = world
    sam_a, sam_b = join(w, w.a, "Sam"), join(w, w.b, "Sam")
    send(w, w.a, sam_a)
    assert w.client.get(f"{API}/table-session", headers=sam_b).json()["rounds"] == []
    assert w.client.get(f"{API}/table-session", headers=sam_b).json()["table_number"] == "B1"


# ------------------------------------------------------------------ staff and closing

def test_staff_see_open_tabs_and_closing_one_ends_it_everywhere(world):
    w = world
    sam = join(w, w.a, "Sam")
    send(w, w.a, sam, qty=2)
    old_token = w.a.table.qr_token
    staff = header(w.a.staff)

    [tab] = w.client.get(f"{API}/admin/table-sessions", params={"restaurant_id": w.a.rid}, headers=staff).json()
    assert (tab["table_number"], tab["guests"], tab["rounds"]) == ("A1", 1, 1) and float(tab["total"]) == pytest.approx(26.4)

    assert w.client.post(f"{API}/admin/table-sessions/{tab['session_id']}/close", params={"restaurant_id": w.a.rid}, headers=staff).status_code == 204
    assert w.client.get(f"{API}/table-session", headers=sam).status_code == 401               # the pass stops working
    assert send(w, w.a, sam).status_code == 401
    w.db.refresh(w.a.table)
    assert w.a.table.status == TableStatus.CLEANING and w.a.table.qr_token != old_token       # cleaning, code replaced
    assert w.client.get(f"{API}/t/{old_token}").status_code == 404                            # a photo of the old QR is useless
    assert w.client.post(f"{API}/admin/table-sessions/{tab['session_id']}/close", params={"restaurant_id": w.a.rid}, headers=staff).status_code == 400

    w.a.table.status = TableStatus.OCCUPIED                                                    # next party sits down
    w.db.flush()
    join(w, w.a, "Lee")
    assert w.db.query(TableSession).filter_by(table_id=w.a.table.id).count() == 2


def test_only_the_restaurants_own_staff_manage_tabs_and_codes(world):
    w = world
    join(w, w.a)
    sid = w.db.query(TableSession).filter_by(table_id=w.a.table.id).one().id
    q = {"restaurant_id": w.a.rid}
    for who, expect in ((None, 401), (w.a.customer, 403), (w.b.admin, 403), (w.b.staff, 403)):
        h = header(who) if who else {}
        assert w.client.get(f"{API}/admin/table-sessions", params=q, headers=h).status_code == expect
        assert w.client.post(f"{API}/admin/table-sessions/{sid}/close", params=q, headers=h).status_code == expect
        assert w.client.get(f"{API}/admin/qr/tables", params=q, headers=h).status_code == expect
    # Bravo's admin naming its own restaurant can't close Alpha's tab or rotate Alpha's table.
    own = {"restaurant_id": w.b.rid}
    assert w.client.post(f"{API}/admin/table-sessions/{sid}/close", params=own, headers=header(w.b.admin)).status_code == 404
    assert w.client.post(f"{API}/admin/tables/{w.a.table.id}/qr/rotate", params=own, headers=header(w.b.admin)).status_code == 404
    assert w.db.get(TableSession, sid).state == OPEN
    # Staff (not admins) may run tabs but not print/rotate codes.
    assert w.client.get(f"{API}/admin/qr/tables", params=q, headers=header(w.a.staff)).status_code == 403


def test_admin_lists_codes_and_rotating_one_kills_the_old_link(world):
    w = world
    admin = header(w.a.admin)
    [row] = w.client.get(f"{API}/admin/qr/tables", params={"restaurant_id": w.a.rid}, headers=admin).json()
    assert row["qr_token"] == w.a.table.qr_token and row["has_open_session"] is False
    new = w.client.post(f"{API}/admin/tables/{w.a.table.id}/qr/rotate", params={"restaurant_id": w.a.rid}, headers=admin).json()
    assert new["qr_token"] != row["qr_token"]
    assert w.client.get(f"{API}/t/{row['qr_token']}").status_code == 404
    assert w.client.get(f"{API}/t/{new['qr_token']}").status_code == 200


def test_the_admin_endpoints_are_off_when_the_flag_is_off(world):
    w = world
    FeatureService(w.db).set(w.a.rid, "qr_table_ordering", False, w.boss)
    assert w.client.get(f"{API}/admin/qr/tables", params={"restaurant_id": w.a.rid}, headers=header(w.a.admin)).status_code == 403
