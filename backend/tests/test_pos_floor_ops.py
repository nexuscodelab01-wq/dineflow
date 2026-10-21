"""Floor ops: split bills, move and merge tabs, course firing and tab names."""

from decimal import Decimal

import pytest

from app.db.session import get_db
from app.main import app
from app.models.enums import OrderStatus, PaymentStatus, TableStatus
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.payment import Payment
from app.models.restaurant_table import RestaurantTable
from app.models.restaurant_user import RestaurantUser
from app.models.table_session import TableSession
from app.services.feature_service import FeatureService
from app.services.table_session_service import TableSessionService
from tests.conftest import override_get_db
from tests.tenants import header, make_tenant

API = "/api/v1"


@pytest.fixture
def world(client, db):
    app.dependency_overrides[get_db] = override_get_db(db)
    a = make_tenant(db, "Alpha")
    for flag in ("pos", "qr_table_ordering", "pos_controls"):
        FeatureService(db).set(a.rid, flag, True, None, actor_label="test")
    second = RestaurantTable(restaurant_id=a.rid, table_number="A2", capacity=4, status=TableStatus.AVAILABLE)
    third = RestaurantTable(restaurant_id=a.rid, table_number="A3", capacity=4, status=TableStatus.AVAILABLE)
    db.add_all([second, third])
    db.commit()
    mid = db.query(RestaurantUser).filter_by(restaurant_id=a.rid, user_id=a.staff.id).one().id
    client.post(f"{API}/admin/devices/staff/{mid}/pin", params={"restaurant_id": a.rid}, headers=header(a.admin), json={"pin": "1111"})
    token = client.post(f"{API}/admin/devices", params={"restaurant_id": a.rid}, headers=header(a.admin), json={"label": "Till"}).json()["device_token"]
    login = client.post(f"{API}/pos/auth/pin-login", headers={"Authorization": f"Bearer {token}"}, json={"pin": "1111"}).json()
    yield type("W", (), {
        "client": client, "db": db, "a": a, "second": second, "third": third,
        "h": {"Authorization": f"Bearer {login['pos_session_token']}"}, "device": {"Authorization": f"Bearer {token}"},
    })
    app.dependency_overrides.clear()


def seat(w, table_id=None, **body):
    r = w.client.post(f"{API}/pos/tables/{table_id or w.a.table.id}/seat", headers=w.h, json={"party_size": 2, **body})
    assert r.status_code in (200, 201), r.text
    return r.json()["session_id"]


def round_(w, sid, qty=1, **line):
    r = w.client.post(f"{API}/pos/table-sessions/{sid}/orders", headers=w.h, json={"items": [{"menu_item_id": w.a.item.id, "quantity": qty, "modifier_option_ids": [], **line}]})
    assert r.status_code == 200, r.text
    return r.json()


def tab(w, sid):
    return w.client.get(f"{API}/pos/table-sessions/{sid}", headers=w.h).json()


def pay_cash(w, sid, **split):
    return w.client.post(f"{API}/pos/table-sessions/{sid}/pay-cash", headers=w.h, json=split or None)


# ---------------------------------------------------------------- split bills

def test_an_even_split_leaves_the_tab_open_until_the_last_share(world):
    w = world
    sid = seat(w)
    round_(w, sid, qty=2)  # 26.40
    assert pay_cash(w, sid, mode="EVEN", parts_remaining=2).status_code == 204
    t = tab(w, sid)
    assert t["paid"] == "13.20" and t["balance"] == "13.20"
    assert w.db.get(TableSession, sid).state == "OPEN"
    assert pay_cash(w, sid, mode="EVEN", parts_remaining=1).status_code == 204  # the last share is whatever is left
    assert w.db.get(TableSession, sid).state == "CLOSED"
    assert [p.amount for p in w.db.query(Payment).filter_by(table_session_id=sid).order_by(Payment.id)] == [Decimal("13.20"), Decimal("13.20")]


def test_a_custom_amount_cannot_exceed_what_is_owed(world):
    w = world
    sid = seat(w)
    round_(w, sid)  # 13.20
    assert pay_cash(w, sid, mode="AMOUNT", amount="50").status_code == 400
    assert pay_cash(w, sid, mode="AMOUNT", amount="5.00").status_code == 204
    assert tab(w, sid)["balance"] == "8.20"
    assert pay_cash(w, sid, mode="AMOUNT").status_code == 400  # an amount is needed


def test_paying_for_just_your_items_includes_their_tax_and_cant_be_repeated(world):
    w = world
    sid = seat(w)
    round_(w, sid)
    round_(w, sid)
    items = [i for r in tab(w, sid)["rounds"] for i in r["items"]]
    assert [i["amount_due"] for i in items] == ["13.20", "13.20"]
    assert pay_cash(w, sid, mode="ITEMS", item_ids=[items[0]["item_id"]]).status_code == 204
    again = pay_cash(w, sid, mode="ITEMS", item_ids=[items[0]["item_id"]])
    assert again.status_code == 400 and "already been paid" in again.json()["detail"]
    assert [i["paid"] for r in tab(w, sid)["rounds"] for i in r["items"]] == [True, False]
    assert pay_cash(w, sid, mode="ITEMS", item_ids=[items[1]["item_id"]]).status_code == 204
    assert w.db.get(TableSession, sid).state == "CLOSED"


def test_items_from_another_tab_cannot_be_paid_here(world):
    w = world
    sid, other = seat(w), seat(w, w.second.id)
    round_(w, sid)
    round_(w, other)
    foreign = tab(w, other)["rounds"][0]["items"][0]["item_id"]
    assert pay_cash(w, sid, mode="ITEMS", item_ids=[foreign]).status_code == 400


def test_a_split_by_card_reports_what_is_left(world):
    w = world
    sid = seat(w)
    round_(w, sid, qty=2)
    first = w.client.post(f"{API}/pos/table-sessions/{sid}/pay-card", headers=w.h, json={"mode": "EVEN", "parts_remaining": 2})
    assert first.status_code == 200, first.text
    assert first.json()["closed"] is False and first.json()["balance"] == "13.20"
    last = w.client.post(f"{API}/pos/table-sessions/{sid}/pay-card", headers=w.h, json={"mode": "FULL"})
    assert last.json()["closed"] is True and last.json()["balance"] == "0.00"


def test_the_guests_own_payment_covers_only_the_balance(world):
    w = world
    sid = seat(w)
    round_(w, sid, qty=2)
    assert pay_cash(w, sid, mode="AMOUNT", amount="10.00").status_code == 204
    result = TableSessionService(w.db).pay(w.db.get(TableSession, sid))  # the mock provider settles at once
    assert result.closed is True
    assert w.db.query(Payment).filter_by(table_session_id=sid).order_by(Payment.id.desc()).first().amount == Decimal("16.40")


def test_refunding_a_split_tab_returns_every_part(world):
    w = world
    sid = seat(w)
    round_(w, sid, qty=2)
    pay_cash(w, sid, mode="EVEN", parts_remaining=2)
    pay_cash(w, sid)
    token = w.client.post(f"{API}/admin/devices", params={"restaurant_id": w.a.rid}, headers=header(w.a.admin), json={"label": "Mgr"}).json()["device_token"]
    mid = w.db.query(RestaurantUser).filter_by(restaurant_id=w.a.rid, user_id=w.a.admin.id).one().id
    w.client.post(f"{API}/admin/devices/staff/{mid}/pin", params={"restaurant_id": w.a.rid}, headers=header(w.a.admin), json={"pin": "2222"})
    admin = {"Authorization": f"Bearer {w.client.post(f'{API}/pos/auth/pin-login', headers={'Authorization': f'Bearer {token}'}, json={'pin': '2222'}).json()['pos_session_token']}"}
    recent = w.client.get(f"{API}/pos/recent-payments", headers=w.h).json()
    assert len(recent) == 1 and recent[0]["amount"] == "26.40"  # one row for the tab, parts summed
    r = w.client.post(f"{API}/pos/table-sessions/{sid}/refund", headers=admin, json={"reason_code": "QUALITY"})
    assert r.status_code == 200 and r.json()["amount"] == "26.40"
    assert {p.status for p in w.db.query(Payment).filter_by(table_session_id=sid)} == {PaymentStatus.REFUNDED}


# ---------------------------------------------------------------- move and merge

def test_a_tab_can_move_to_a_free_table(world):
    w = world
    sid = seat(w)
    round_(w, sid)
    assert w.client.post(f"{API}/pos/table-sessions/{sid}/move", headers=w.h, json={"table_id": w.second.id}).status_code == 204
    assert w.db.get(TableSession, sid).table_id == w.second.id
    busy = seat(w, w.third.id)
    assert busy
    assert w.client.post(f"{API}/pos/table-sessions/{sid}/move", headers=w.h, json={"table_id": w.third.id}).status_code == 400  # occupied


def test_two_tabs_merge_into_one(world):
    w = world
    a, b = seat(w), seat(w, w.second.id)
    round_(w, a)
    round_(w, b, qty=2)
    assert w.client.post(f"{API}/pos/table-sessions/{b}/merge", headers=w.h, json={"into_session_id": a}).status_code == 204
    merged = tab(w, a)
    assert [r["round_no"] for r in merged["rounds"]] == [1, 2] and merged["total"] == "39.60"
    assert w.db.get(TableSession, b).state == "CLOSED"
    assert w.db.get(RestaurantTable, w.second.id).status == TableStatus.CLEANING
    assert w.db.query(Order).filter(Order.table_session_id == a).count() == 2


def test_merge_refusals(world):
    w = world
    a, b = seat(w), seat(w, w.second.id)
    round_(w, a, qty=2)
    round_(w, b)
    assert w.client.post(f"{API}/pos/table-sessions/{a}/merge", headers=w.h, json={"into_session_id": a}).status_code == 400
    pay_cash(w, a, mode="AMOUNT", amount="5")  # part-paid
    assert w.client.post(f"{API}/pos/table-sessions/{a}/merge", headers=w.h, json={"into_session_id": b}).status_code == 400
    assert w.client.post(f"{API}/pos/table-sessions/{b}/merge", headers=w.h, json={"into_session_id": a}).status_code == 400
    assert w.client.post(f"{API}/pos/table-sessions/{b}/merge", headers=w.h, json={"into_session_id": 999999}).status_code == 404


def test_another_restaurants_tab_cannot_be_merged_or_moved(world):
    w = world
    sid = seat(w)
    other = make_tenant(w.db, "Bravo")
    FeatureService(w.db).set(other.rid, "pos", True, None, actor_label="test")
    foreign = TableSession(restaurant_id=other.rid, table_id=other.table.id)
    w.db.add(foreign)
    w.db.commit()
    assert w.client.post(f"{API}/pos/table-sessions/{sid}/merge", headers=w.h, json={"into_session_id": foreign.id}).status_code == 404
    assert w.client.post(f"{API}/pos/table-sessions/{sid}/move", headers=w.h, json={"table_id": other.table.id}).status_code == 404


# ---------------------------------------------------------------- courses

def kitchen(w):
    board = w.client.get(f"{API}/admin/kitchen", params={"restaurant_id": w.a.rid}, headers=header(w.a.admin)).json()
    return [i for col in board.values() for o in col for i in o["items"]]


def test_a_held_course_stays_off_the_kitchen_screen_until_fired(world):
    w = world
    sid = seat(w)
    w.client.post(f"{API}/pos/table-sessions/{sid}/orders", headers=w.h, json={"items": [
        {"menu_item_id": w.a.item.id, "quantity": 1, "modifier_option_ids": [], "course": 1},
        {"menu_item_id": w.a.item.id, "quantity": 2, "modifier_option_ids": [], "course": 2},
    ]})
    assert [i["quantity"] for i in kitchen(w)] == [1]  # only course 1 is being cooked
    lines = tab(w, sid)["rounds"][0]["items"]
    assert sorted((i["course"], i["held"]) for i in lines) == [(1, False), (2, True)]
    fired = w.client.post(f"{API}/pos/table-sessions/{sid}/fire", headers=w.h, json={"course": 2})
    assert fired.status_code == 200 and fired.json()["fired"] == 1
    assert sorted(i["quantity"] for i in kitchen(w)) == [1, 2]
    assert w.client.post(f"{API}/pos/table-sessions/{sid}/fire", headers=w.h, json={"course": 2}).status_code == 400  # nothing held now


def test_firing_a_course_wakes_a_ticket_that_had_been_finished(world):
    w = world
    sid = seat(w)
    w.client.post(f"{API}/pos/table-sessions/{sid}/orders", headers=w.h, json={"items": [
        {"menu_item_id": w.a.item.id, "quantity": 1, "modifier_option_ids": [], "course": 1},
        {"menu_item_id": w.a.item.id, "quantity": 1, "modifier_option_ids": [], "course": 2},
    ]})
    order = w.db.query(Order).filter_by(table_session_id=sid).one()
    w.client.post(f"{API}/admin/kitchen/orders/{order.id}/bump", params={"restaurant_id": w.a.rid}, headers=header(w.a.admin))
    w.db.refresh(order)
    assert order.status == OrderStatus.READY  # course 1 done; course 2 isn't on the screen so it doesn't hold the ticket
    w.client.post(f"{API}/pos/table-sessions/{sid}/fire", headers=w.h, json={"course": 2})
    w.db.refresh(order)
    assert order.status == OrderStatus.PREPARING
    assert all(not i.held for i in w.db.query(OrderItem).filter_by(order_id=order.id))


def test_a_customers_course_request_is_ignored(world):
    w = world
    r = w.client.post(f"{API}/orders", headers=header(w.a.customer), json={
        "restaurant_id": w.a.rid, "order_type": "PICKUP", "customer_name": "x", "customer_email": w.a.customer.email,
        "items": [{"menu_item_id": w.a.item.id, "quantity": 1, "modifier_option_ids": [], "course": 3}],
    })
    assert r.status_code == 201, r.text
    item = w.db.query(OrderItem).filter_by(order_id=r.json()["id"]).one()
    assert item.course == 1 and item.held is False


# ---------------------------------------------------------------- tab names

def test_a_tab_can_be_named_when_seated(world):
    w = world
    sid = seat(w, tab_name="Mike at the bar")
    assert tab(w, sid)["tab_name"] == "Mike at the bar"
    open_tabs = w.client.get(f"{API}/pos/table-sessions/open", headers=w.device).json()["sessions"]
    assert open_tabs[0]["tab_name"] == "Mike at the bar"
