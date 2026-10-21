"""POS controls: voids, comps, discounts and refunds with reasons, role permissions and a manager's PIN."""

from decimal import Decimal

import pytest

from app.db.session import get_db
from app.main import app
from app.models.enums import OrderStatus, PaymentStatus
from app.models.order import Order
from app.models.order_adjustment import OrderAdjustment
from app.models.payment import Payment
from app.models.restaurant_user import RestaurantUser
from app.services.feature_service import FeatureService
from tests.conftest import override_get_db
from tests.tenants import header, make_tenant

API = "/api/v1"


@pytest.fixture
def world(client, db):
    app.dependency_overrides[get_db] = override_get_db(db)
    a = make_tenant(db, "Alpha")
    for flag in ("pos", "qr_table_ordering", "pos_controls"):
        FeatureService(db).set(a.rid, flag, True, None, actor_label="test")
    yield type("W", (), {"client": client, "db": db, "a": a})
    app.dependency_overrides.clear()


class Till:
    """One paired device that both a server (staff) and a manager (admin) can PIN into."""

    def __init__(self, w):
        self.w = w
        self.token = w.client.post(f"{API}/admin/devices", params={"restaurant_id": w.a.rid}, headers=header(w.a.admin), json={"label": "Till"}).json()["device_token"]
        self.device = {"Authorization": f"Bearer {self.token}"}

    def login(self, user, pin):
        w = self.w
        mid = w.db.query(RestaurantUser).filter_by(restaurant_id=w.a.rid, user_id=user.id).one().id
        w.client.post(f"{API}/admin/devices/staff/{mid}/pin", params={"restaurant_id": w.a.rid}, headers=header(w.a.admin), json={"pin": pin})
        login = w.client.post(f"{API}/pos/auth/pin-login", headers=self.device, json={"pin": pin})
        assert login.status_code == 200, login.text
        return {"Authorization": f"Bearer {login.json()['pos_session_token']}"}


@pytest.fixture
def till(world):
    t = Till(world)
    t.staff = t.login(world.a.staff, "1111")
    t.admin = t.login(world.a.admin, "2222")
    return t


def tab_with_two_burgers(w, till, rounds=1):
    seated = w.client.post(f"{API}/pos/tables/{w.a.table.id}/seat", headers=till.staff, json={"party_size": 2}).json()["session_id"]
    for _ in range(rounds):
        r = w.client.post(f"{API}/pos/table-sessions/{seated}/orders", headers=till.staff, json={"items": [{"menu_item_id": w.a.item.id, "quantity": 2, "modifier_option_ids": []}]})
        assert r.status_code == 200, r.text
    return seated


def detail(w, till, session_id):
    return w.client.get(f"{API}/pos/table-sessions/{session_id}", headers=till.staff).json()


def first_item_id(w, till, session_id):
    return detail(w, till, session_id)["rounds"][0]["items"][0]["item_id"]


REASON = {"reason_code": "WRONG_ITEM"}


# ---------------------------------------------------------------- approval

def test_staff_need_a_managers_approval_to_void(world, till):
    w = world
    item = first_item_id(w, till, tab_with_two_burgers(w, till))
    r = w.client.post(f"{API}/pos/order-items/{item}/void", headers=till.staff, json=REASON)
    assert r.status_code == 403 and "approval" in r.json()["detail"].lower()


def test_a_managers_pin_unlocks_exactly_one_kind_of_action(world, till):
    w = world
    sid = tab_with_two_burgers(w, till)
    item = first_item_id(w, till, sid)
    token = w.client.post(f"{API}/pos/authorize", headers=till.staff, json={"pin": "2222", "action": "void"}).json()["token"]
    ok = w.client.post(f"{API}/pos/order-items/{item}/void", headers={**till.staff, "X-Manager-Override": token}, json=REASON)
    assert ok.status_code == 200, ok.text
    adjustment = w.db.query(OrderAdjustment).one()
    assert adjustment.kind == "VOID" and adjustment.authorized_by_user_id == w.a.admin.id and adjustment.staff_user_id == w.a.staff.id
    # The same approval doesn't cover a comp.
    sid2 = tab_with_two_burgers(w, till, rounds=1)
    item2 = detail(w, till, sid2)["rounds"][-1]["items"][0]["item_id"] if sid2 else None
    comp = w.client.post(f"{API}/pos/order-items/{item2}/comp", headers={**till.staff, "X-Manager-Override": token}, json={"reason_code": "MANAGER_COMP"})
    assert comp.status_code == 403


def test_a_staff_pin_cannot_approve_a_refund_and_a_wrong_pin_is_refused(world, till):
    w = world
    assert w.client.post(f"{API}/pos/authorize", headers=till.staff, json={"pin": "1111", "action": "refund"}).status_code == 403
    assert w.client.post(f"{API}/pos/authorize", headers=till.staff, json={"pin": "9999", "action": "void"}).status_code == 400


def test_an_admin_can_void_on_their_own_authority(world, till):
    w = world
    item = first_item_id(w, till, tab_with_two_burgers(w, till))
    r = w.client.post(f"{API}/pos/order-items/{item}/void", headers=till.admin, json=REASON)
    assert r.status_code == 200, r.text
    assert w.db.query(OrderAdjustment).one().authorized_by_user_id is None


def test_the_restaurant_can_let_staff_void_themselves(world, till):
    from app.models.restaurant import Restaurant

    w = world
    w.db.get(Restaurant, w.a.rid).pos_staff_permissions = {"void": True, "comp": False, "refund": False, "discount_max_pct": 10}
    w.db.commit()
    item = first_item_id(w, till, tab_with_two_burgers(w, till))
    assert w.client.post(f"{API}/pos/order-items/{item}/void", headers=till.staff, json=REASON).status_code == 200


# ---------------------------------------------------------------- voids

def test_voiding_part_of_a_line_reprices_the_round(world, till):
    w = world
    sid = tab_with_two_burgers(w, till)
    item = first_item_id(w, till, sid)
    r = w.client.post(f"{API}/pos/order-items/{item}/void", headers=till.admin, json={**REASON, "quantity": 1})
    assert r.status_code == 200, r.text
    assert r.json()["amount"] == "12.00" and r.json()["order_total"] == "13.20"  # one burger left: 12.00 + 10% tax
    assert detail(w, till, sid)["total"] == "13.20"


def test_voiding_the_last_line_cancels_the_round(world, till):
    w = world
    sid = tab_with_two_burgers(w, till)
    item = first_item_id(w, till, sid)
    w.client.post(f"{API}/pos/order-items/{item}/void", headers=till.admin, json=REASON)
    order = w.db.query(Order).one()
    assert order.status == OrderStatus.CANCELLED and order.total == Decimal("0.00")
    assert detail(w, till, sid)["total"] == "0.00"


def test_you_cannot_void_more_than_was_ordered_or_without_a_reason(world, till):
    w = world
    item = first_item_id(w, till, tab_with_two_burgers(w, till))
    assert w.client.post(f"{API}/pos/order-items/{item}/void", headers=till.admin, json={**REASON, "quantity": 5}).status_code == 400
    assert w.client.post(f"{API}/pos/order-items/{item}/void", headers=till.admin, json={"reason_code": "NOPE"}).status_code == 400
    assert w.client.post(f"{API}/pos/order-items/{item}/void", headers=till.admin, json={"reason_code": "OTHER"}).status_code == 400
    assert w.client.post(f"{API}/pos/order-items/{item}/void", headers=till.admin, json={"reason_code": "OTHER", "note": "Guest left"}).status_code == 200


def test_a_paid_counter_order_cannot_be_voided_only_refunded(world, till):
    w = world
    created = w.client.post(f"{API}/pos/orders", headers=till.staff, json={"items": [{"menu_item_id": w.a.item.id, "quantity": 1, "modifier_option_ids": []}]}).json()
    w.client.post(f"{API}/pos/orders/{created['order_id']}/pay-cash", headers=till.staff)
    item = w.db.query(Order).filter_by(id=created["order_id"]).one().items[0].id
    assert w.client.post(f"{API}/pos/order-items/{item}/void", headers=till.admin, json=REASON).status_code == 400


# ---------------------------------------------------------------- comps and discounts

def test_a_comp_makes_the_line_free_and_is_recorded(world, till):
    w = world
    sid = tab_with_two_burgers(w, till)
    item = first_item_id(w, till, sid)
    r = w.client.post(f"{API}/pos/order-items/{item}/comp", headers=till.admin, json={"reason_code": "SERVICE_RECOVERY"})
    assert r.status_code == 200 and r.json()["amount"] == "24.00" and r.json()["order_total"] == "0.00"
    assert w.client.post(f"{API}/pos/order-items/{item}/comp", headers=till.admin, json={"reason_code": "SERVICE_RECOVERY"}).status_code == 400  # already free
    line = detail(w, till, sid)["rounds"][0]["items"][0]
    assert line["line_total"] == "0.00" and line["discount_amount"] == "24.00"


def test_staff_discount_within_their_ceiling_needs_no_approval_above_it_does(world, till):
    w = world
    sid = tab_with_two_burgers(w, till)
    order_id = detail(w, till, sid)["rounds"][0]["order_id"]
    small = w.client.post(f"{API}/pos/orders/{order_id}/discount", headers=till.staff, json={"reason_code": "LOYALTY", "percent": "10"})
    assert small.status_code == 200, small.text
    assert small.json()["amount"] == "2.40" and small.json()["order_total"] == "23.76"  # 21.60 + 10%
    big = w.client.post(f"{API}/pos/orders/{order_id}/discount", headers=till.staff, json={"reason_code": "LOYALTY", "percent": "50"})
    assert big.status_code == 403
    token = w.client.post(f"{API}/pos/authorize", headers=till.staff, json={"pin": "2222", "action": "discount"}).json()["token"]
    approved = w.client.post(f"{API}/pos/orders/{order_id}/discount", headers={**till.staff, "X-Manager-Override": token}, json={"reason_code": "MANAGER", "percent": "50"})
    assert approved.status_code == 200, approved.text


def test_a_tab_discount_is_spread_across_every_round(world, till):
    w = world
    sid = tab_with_two_burgers(w, till, rounds=2)
    r = w.client.post(f"{API}/pos/table-sessions/{sid}/discount", headers=till.admin, json={"reason_code": "MANAGER", "percent": "25"})
    assert r.status_code == 200, r.text
    assert r.json()["amount"] == "12.00"
    assert detail(w, till, sid)["total"] == "39.60"  # 48.00 − 12.00 = 36.00, + 10% tax


def test_a_discount_needs_exactly_one_of_percent_or_amount(world, till):
    w = world
    order_id = detail(w, till, tab_with_two_burgers(w, till))["rounds"][0]["order_id"]
    both = w.client.post(f"{API}/pos/orders/{order_id}/discount", headers=till.admin, json={"reason_code": "MANAGER", "percent": "5", "amount": "1"})
    assert both.status_code == 422
    flat = w.client.post(f"{API}/pos/orders/{order_id}/discount", headers=till.admin, json={"reason_code": "MANAGER", "amount": "4.00"})
    assert flat.status_code == 200 and flat.json()["amount"] == "4.00"


# ---------------------------------------------------------------- refunds

def _paid_counter_order(w, till):
    created = w.client.post(f"{API}/pos/orders", headers=till.staff, json={"items": [{"menu_item_id": w.a.item.id, "quantity": 1, "modifier_option_ids": []}]}).json()
    assert w.client.post(f"{API}/pos/orders/{created['order_id']}/pay-cash", headers=till.staff).status_code == 204
    return created["order_id"]


def test_a_refund_needs_permission_then_reverses_the_payment(world, till):
    w = world
    order_id = _paid_counter_order(w, till)
    assert w.client.post(f"{API}/pos/orders/{order_id}/refund", headers=till.staff, json={"reason_code": "WRONG_ORDER"}).status_code == 403
    r = w.client.post(f"{API}/pos/orders/{order_id}/refund", headers=till.admin, json={"reason_code": "WRONG_ORDER"})
    assert r.status_code == 200, r.text
    assert w.db.query(Payment).filter_by(order_id=order_id).one().status == PaymentStatus.REFUNDED
    assert w.db.get(Order, order_id).status == OrderStatus.CANCELLED
    assert w.client.post(f"{API}/pos/orders/{order_id}/refund", headers=till.admin, json={"reason_code": "WRONG_ORDER"}).status_code == 400  # nothing left to refund


def test_refunding_cash_from_a_later_shift_reduces_the_drawer(world, till):
    w = world
    first = w.client.post(f"{API}/pos/shifts/open", headers=till.staff, json={"starting_float": "50.00"}).json()["shift_id"]
    order_id = _paid_counter_order(w, till)
    w.client.post(f"{API}/pos/shifts/{first}/close", headers=till.staff, json={"counted_cash": "63.20"})
    second = w.client.post(f"{API}/pos/shifts/open", headers=till.staff, json={"starting_float": "100.00"}).json()["shift_id"]
    assert w.client.post(f"{API}/pos/orders/{order_id}/refund", headers=till.admin, json={"reason_code": "QUALITY"}).status_code == 200
    z = w.client.post(f"{API}/pos/shifts/{second}/close", headers=till.staff, json={"counted_cash": "86.80"}).json()
    assert Decimal(z["expected_cash"]) == Decimal("86.80") and Decimal(z["variance"]) == Decimal("0.00")  # 100 − 13.20 handed back


def test_refunding_a_settled_tab(world, till):
    w = world
    sid = tab_with_two_burgers(w, till)
    assert w.client.post(f"{API}/pos/table-sessions/{sid}/refund", headers=till.admin, json={"reason_code": "QUALITY"}).status_code == 400  # not settled yet
    w.client.post(f"{API}/pos/table-sessions/{sid}/pay-cash", headers=till.staff)
    recent = w.client.get(f"{API}/pos/recent-payments", headers=till.staff).json()
    assert recent[0]["kind"] == "TAB" and recent[0]["amount"] == "26.40"
    assert w.client.post(f"{API}/pos/table-sessions/{sid}/refund", headers=till.admin, json={"reason_code": "QUALITY"}).status_code == 200


# ---------------------------------------------------------------- reports, gating

def test_the_admin_report_lists_adjustments_with_who_and_why(world, till):
    from datetime import UTC, datetime, timedelta

    w = world
    item = first_item_id(w, till, tab_with_two_burgers(w, till))
    w.client.post(f"{API}/pos/order-items/{item}/void", headers=till.admin, json={"reason_code": "KITCHEN_ERROR", "note": "burnt"})
    now = datetime.now(UTC)
    r = w.client.get(f"{API}/admin/adjustments", params={"restaurant_id": w.a.rid, "start": (now - timedelta(days=1)).isoformat(), "end": (now + timedelta(hours=1)).isoformat()}, headers=header(w.a.admin))
    assert r.status_code == 200, r.text
    row = r.json()[0]
    assert row["kind"] == "VOID" and row["reason_code"] == "KITCHEN_ERROR" and row["note"] == "burnt" and row["staff"] == "Alpha"


def test_controls_need_the_flag(world, till):
    w = world
    item = first_item_id(w, till, tab_with_two_burgers(w, till))
    FeatureService(w.db).set(w.a.rid, "pos_controls", False, None, actor_label="test")
    w.db.commit()
    assert w.client.post(f"{API}/pos/order-items/{item}/void", headers=till.admin, json=REASON).status_code == 403


def test_the_staff_permission_ceiling_is_validated(world):
    r = world.client.patch(f"{API}/admin/settings", params={"restaurant_id": world.a.rid}, headers=header(world.a.admin), json={"pos_staff_permissions": {"discount_max_pct": 150}})
    assert r.status_code == 422


def test_another_restaurants_till_cannot_touch_this_tabs_lines_or_payments(world, till):
    w = world
    sid = tab_with_two_burgers(w, till)
    item = first_item_id(w, till, sid)
    order_id = detail(w, till, sid)["rounds"][0]["order_id"]
    b = make_tenant(w.db, "Bravo")
    for flag in ("pos", "pos_controls"):
        FeatureService(w.db).set(b.rid, flag, True, None, actor_label="test")
    token = w.client.post(f"{API}/admin/devices", params={"restaurant_id": b.rid}, headers=header(b.admin), json={"label": "Till"}).json()["device_token"]
    mid = w.db.query(RestaurantUser).filter_by(restaurant_id=b.rid, user_id=b.admin.id).one().id
    w.client.post(f"{API}/admin/devices/staff/{mid}/pin", params={"restaurant_id": b.rid}, headers=header(b.admin), json={"pin": "3333"})
    login = w.client.post(f"{API}/pos/auth/pin-login", headers={"Authorization": f"Bearer {token}"}, json={"pin": "3333"}).json()
    theirs = {"Authorization": f"Bearer {login['pos_session_token']}"}
    assert w.client.post(f"{API}/pos/order-items/{item}/void", headers=theirs, json=REASON).status_code == 404
    assert w.client.post(f"{API}/pos/order-items/{item}/comp", headers=theirs, json={"reason_code": "MANAGER_COMP"}).status_code == 404
    assert w.client.post(f"{API}/pos/orders/{order_id}/discount", headers=theirs, json={"reason_code": "MANAGER", "percent": "5"}).status_code == 404
    assert w.client.post(f"{API}/pos/orders/{order_id}/refund", headers=theirs, json={"reason_code": "QUALITY"}).status_code == 404
    assert w.client.post(f"{API}/pos/table-sessions/{sid}/discount", headers=theirs, json={"reason_code": "MANAGER", "percent": "5"}).status_code == 404
    assert w.client.get(f"{API}/pos/table-sessions/{sid}", headers=theirs).status_code == 404
    assert w.db.query(OrderAdjustment).count() == 0
