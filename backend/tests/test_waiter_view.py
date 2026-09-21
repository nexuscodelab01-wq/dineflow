"""Waiter view: the floor with live tabs, staff sending rounds for a table, and moving a tab to another table."""

import pytest

from app.models.enums import TableStatus
from app.models.order import Order
from app.models.restaurant_table import RestaurantTable
from app.models.table_session import TableSession
from app.services.feature_service import FeatureService
from tests.tenants import header
from tests.test_live_status import announced  # noqa: F401  (fixture)
from tests.test_service_requests import ask
from tests.test_table_ordering import join, send, world  # noqa: F401  (world is a fixture)

API = "/api/v1"


def floor(w, tenant, who=None):
    return w.client.get(f"{API}/admin/waiter/floor", params={"restaurant_id": tenant.rid}, headers=header(who or tenant.staff))


def session_id(w, tenant):
    return w.db.query(TableSession).filter_by(table_id=tenant.table.id, state="OPEN").one().id


def staff_round(w, tenant, sid, qty=1, key=None, who=None, item=None):
    headers = {**header(who or tenant.staff), **({"Idempotency-Key": key} if key else {})}
    return w.client.post(f"{API}/admin/table-sessions/{sid}/orders", params={"restaurant_id": tenant.rid}, headers=headers,
                         json={"items": [{"menu_item_id": (item or tenant.item).id, "quantity": qty, "modifier_option_ids": []}]})


@pytest.fixture
def second_table(world):
    w = world
    t = RestaurantTable(restaurant_id=w.a.rid, table_number="A2", capacity=4, status=TableStatus.AVAILABLE)
    w.db.add(t)
    w.db.flush()
    return t


# ------------------------------------------------------------------ the floor

def test_the_floor_shows_every_table_and_the_live_tab_on_it(world, second_table):
    w = world
    sam = join(w, w.a, "Sam")
    send(w, w.a, sam, qty=2)
    ask(w, sam, "WAITER")
    rows = {r["table_number"]: r for r in floor(w, w.a).json()}
    assert set(rows) == {"A1", "A2"} and rows["A2"]["session"] is None
    tab = rows["A1"]["session"]
    assert (tab["guests"], tab["rounds"], tab["ready_rounds"], tab["requests"]) == (1, 1, 0, ["WAITER"])
    assert float(tab["total"]) == pytest.approx(26.4) and tab["waiting_since"] is not None
    assert rows["A1"]["status"] == "OCCUPIED" and rows["A2"]["status"] == "AVAILABLE"


def test_finished_rounds_are_counted_until_they_are_served(world):
    w = world
    sam = join(w, w.a, "Sam")
    oid = send(w, w.a, sam).json()["order_id"]
    for status in ("PREPARING", "READY"):
        w.client.patch(f"{API}/admin/orders/{oid}/status", params={"restaurant_id": w.a.rid}, headers=header(w.a.staff), json={"status": status})
    assert floor(w, w.a).json()[0]["session"]["ready_rounds"] == 1
    w.client.patch(f"{API}/admin/orders/{oid}/status", params={"restaurant_id": w.a.rid}, headers=header(w.a.staff), json={"status": "COMPLETED"})   # served
    assert floor(w, w.a).json()[0]["session"]["ready_rounds"] == 0


def test_the_floor_and_tab_details_stay_inside_the_restaurant_and_role(world):
    w = world
    join(w, w.a, "Sam")
    sid = session_id(w, w.a)
    assert floor(w, w.a, w.a.customer).status_code == 403
    assert floor(w, w.a, w.b.staff).status_code == 403
    assert [r["table_number"] for r in floor(w, w.b).json()] == ["B1"] and floor(w, w.b).json()[0]["session"] is None
    q = {"restaurant_id": w.a.rid}
    detail = w.client.get(f"{API}/admin/table-sessions/{sid}", params=q, headers=header(w.a.staff))
    assert detail.status_code == 200 and detail.json()["table_number"] == "A1" and detail.json()["guests"] == ["Sam"]
    assert w.client.get(f"{API}/admin/table-sessions/{sid}", params={"restaurant_id": w.b.rid}, headers=header(w.b.staff)).status_code == 404
    assert w.client.get(f"{API}/admin/table-sessions/{sid}", params=q, headers=header(w.a.customer)).status_code == 403


# ------------------------------------------------------------------ staff rounds

def test_a_waiter_can_send_a_round_for_the_table(world):
    w = world
    sam = join(w, w.a, "Sam")
    sid = session_id(w, w.a)
    r = staff_round(w, w.a, sid, qty=2)
    assert r.status_code == 201, r.text
    assert r.json()["ordered_by"] == "Staff" and r.json()["round_no"] == 1
    order = w.db.get(Order, r.json()["order_id"])
    assert order.customer_name.endswith("(staff)") and order.session_guest_id is None and order.table_id == w.a.table.id
    assert order.status_history[-1].changed_by_user_id == w.a.staff.id
    assert w.client.get(f"{API}/table-session", headers=sam).json()["rounds"][0]["ordered_by"] == "Staff"     # the guests see it too
    board = w.client.get(f"{API}/admin/kitchen", params={"restaurant_id": w.a.rid}, headers=header(w.a.staff)).json()
    assert any(o["id"] == order.id and o["table_number"] == "A1" for col in board.values() for o in col)


def test_staff_rounds_are_retry_safe_and_checked_like_guest_rounds(world):
    w = world
    join(w, w.a)
    sid = session_id(w, w.a)
    a, b = staff_round(w, w.a, sid, key="k1"), staff_round(w, w.a, sid, key="k1")
    assert a.json()["order_id"] == b.json()["order_id"]
    assert staff_round(w, w.a, sid, item=w.b.item).status_code == 400          # another restaurant's dish
    assert staff_round(w, w.a, sid, who=w.a.customer).status_code == 403
    assert staff_round(w, w.a, sid, who=w.b.staff).status_code == 403
    assert w.client.post(f"{API}/admin/table-sessions/{sid}/orders", params={"restaurant_id": w.b.rid}, headers=header(w.b.staff),
                         json={"items": [{"menu_item_id": w.b.item.id, "quantity": 1, "modifier_option_ids": []}]}).status_code == 404


# ------------------------------------------------------------------ moving a tab

def test_a_tab_can_move_to_a_free_table_and_everything_follows(world, second_table, announced):
    w = world
    sam = join(w, w.a, "Sam")
    send(w, w.a, sam)
    ask(w, sam, "WAITER")
    sid = session_id(w, w.a)
    old_token = w.a.table.qr_token
    announced.clear()

    r = w.client.post(f"{API}/admin/table-sessions/{sid}/transfer", params={"restaurant_id": w.a.rid}, headers=header(w.a.staff), json={"table_id": second_table.id})
    assert r.status_code == 204, r.text
    w.db.refresh(w.a.table)
    w.db.refresh(second_table)
    assert (second_table.status, w.a.table.status) == (TableStatus.OCCUPIED, TableStatus.CLEANING) and w.a.table.qr_token != old_token
    assert {(t, e) for t, e, _ in announced} >= {(f"session:{sid}", "session.transferred")}

    assert w.client.get(f"{API}/table-session", headers=sam).json()["table_number"] == "A2"                   # the guest's pass still works
    board = w.client.get(f"{API}/admin/kitchen", params={"restaurant_id": w.a.rid}, headers=header(w.a.staff)).json()
    assert all(o["table_number"] == "A2" for col in board.values() for o in col)                               # the kitchen calls it A2
    [req] = w.client.get(f"{API}/admin/service-requests", params={"restaurant_id": w.a.rid}, headers=header(w.a.staff)).json()
    assert req["table_number"] == "A2"
    rows = {r["table_number"]: r for r in floor(w, w.a).json()}
    assert rows["A2"]["session"]["session_id"] == sid and rows["A1"]["session"] is None

    # another guest scanning the new table's code joins the same tab
    joined = w.client.post(f"{API}/t/{second_table.qr_token}/join", params={"restaurant_id": w.a.rid}, json={"name": "Kim"})
    assert joined.status_code == 200 and joined.json()["session_id"] == sid


def test_a_tab_cannot_move_somewhere_it_should_not(world, second_table):
    w = world
    join(w, w.a)
    sid = session_id(w, w.a)
    post = lambda table_id, who=None, tenant=None: w.client.post(  # noqa: E731
        f"{API}/admin/table-sessions/{sid}/transfer", params={"restaurant_id": (tenant or w.a).rid}, headers=header(who or w.a.staff), json={"table_id": table_id})
    assert post(w.a.table.id).status_code == 400                                   # already there
    assert post(w.b.table.id).status_code == 404                                   # another restaurant's table
    second_table.is_active = False
    w.db.flush()
    assert post(second_table.id).status_code == 400                                # out of service
    second_table.is_active = True
    w.db.add(TableSession(restaurant_id=w.a.rid, table_id=second_table.id))
    w.db.flush()
    busy = post(second_table.id)
    assert busy.status_code == 400 and "open tab" in busy.json()["detail"]         # someone is already there
    assert post(second_table.id, who=w.a.customer).status_code == 403
    assert w.db.query(TableSession).filter_by(id=sid).one().table_id == w.a.table.id


def test_the_waiter_view_is_off_when_the_flag_is_off(world):
    w = world
    FeatureService(w.db).set(w.a.rid, "qr_table_ordering", False, w.boss)
    assert floor(w, w.a).status_code == 403
