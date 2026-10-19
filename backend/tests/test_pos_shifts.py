"""Shift open/close and cash reconciliation (Z-report) — one open shift per device, cash/card totals and
variance computed from Payment.shift_id, never a time-window query (so concurrent tills don't mix)."""

from decimal import Decimal

import pytest

from app.db.session import get_db
from app.main import app
from app.models.enums import OrderStatus
from app.models.order import Order
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


def ring_cash_order(w, staff_headers, quantity=1):
    created = w.client.post(f"{API}/pos/orders", headers=staff_headers, json={"items": [{"menu_item_id": w.a.item.id, "quantity": quantity, "modifier_option_ids": []}]})
    assert created.status_code == 201, created.text
    order_id = created.json()["order_id"]
    r = w.client.post(f"{API}/pos/orders/{order_id}/pay-cash", headers=staff_headers)
    assert r.status_code == 204, r.text
    return order_id


def test_open_ring_cash_close_has_zero_variance(world):
    w = world
    staff_headers = pos_session(w, w.a, w.a.staff)

    opened = w.client.post(f"{API}/pos/shifts/open", headers=staff_headers, json={"starting_float": "50.00"})
    assert opened.status_code == 201, opened.text
    shift_id = opened.json()["shift_id"]

    ring_cash_order(w, staff_headers, quantity=1)  # $12 * 1.10 tax = $13.20
    order_total = Decimal("12.00") * Decimal("1.10")

    closed = w.client.post(f"{API}/pos/shifts/{shift_id}/close", headers=staff_headers, json={"counted_cash": str(Decimal("50.00") + order_total)})
    assert closed.status_code == 200, closed.text
    report = closed.json()
    assert Decimal(report["expected_cash"]) == Decimal("50.00") + order_total
    assert Decimal(report["variance"]) == Decimal("0.00")
    assert report["order_count"] == 1


def test_cannot_open_a_second_shift_on_the_same_device(world):
    w = world
    staff_headers = pos_session(w, w.a, w.a.staff)
    r1 = w.client.post(f"{API}/pos/shifts/open", headers=staff_headers, json={"starting_float": "50.00"})
    assert r1.status_code == 201

    r2 = w.client.post(f"{API}/pos/shifts/open", headers=staff_headers, json={"starting_float": "20.00"})
    assert r2.status_code == 409


def test_concurrent_devices_do_not_mix_cash(world):
    """The whole reason shift_id exists over a time-window query: two tills open at once must not see
    each other's cash."""
    w = world
    staff_a = pos_session(w, w.a, w.a.staff, pin="1111")
    staff_b = pos_session(w, w.a, w.a.staff, pin="2222")

    shift_a = w.client.post(f"{API}/pos/shifts/open", headers=staff_a, json={"starting_float": "50.00"}).json()["shift_id"]
    shift_b = w.client.post(f"{API}/pos/shifts/open", headers=staff_b, json={"starting_float": "100.00"}).json()["shift_id"]

    order_a = ring_cash_order(w, staff_a, quantity=1)
    order_b = ring_cash_order(w, staff_b, quantity=2)

    payment_a = w.db.query(Payment).filter_by(order_id=order_a).one()
    payment_b = w.db.query(Payment).filter_by(order_id=order_b).one()
    assert payment_a.shift_id == shift_a
    assert payment_b.shift_id == shift_b
    assert payment_a.shift_id != payment_b.shift_id

    report_a = w.client.post(f"{API}/pos/shifts/{shift_a}/close", headers=staff_a, json={"counted_cash": "63.20"}).json()
    report_b = w.client.post(f"{API}/pos/shifts/{shift_b}/close", headers=staff_b, json={"counted_cash": "126.40"}).json()
    assert report_a["order_count"] == 1
    assert report_b["order_count"] == 1
    assert Decimal(report_a["cash_total"]) == Decimal("12.00") * Decimal("1.10")
    assert Decimal(report_b["cash_total"]) == Decimal("12.00") * 2 * Decimal("1.10")


def test_cash_movement_affects_expected_cash(world):
    w = world
    staff_headers = pos_session(w, w.a, w.a.staff)
    shift_id = w.client.post(f"{API}/pos/shifts/open", headers=staff_headers, json={"starting_float": "50.00"}).json()["shift_id"]

    r = w.client.post(f"{API}/pos/shifts/{shift_id}/cash-movement", headers=staff_headers, json={"kind": "PAID_OUT", "amount": "10.00", "reason": "Driver tip"})
    assert r.status_code == 204, r.text

    closed = w.client.post(f"{API}/pos/shifts/{shift_id}/close", headers=staff_headers, json={"counted_cash": "40.00"})
    assert closed.status_code == 200, closed.text
    assert Decimal(closed.json()["variance"]) == Decimal("0.00")


def test_closing_a_mismatched_shift_id_is_404(world):
    w = world
    staff_headers = pos_session(w, w.a, w.a.staff)
    w.client.post(f"{API}/pos/shifts/open", headers=staff_headers, json={"starting_float": "50.00"})

    r = w.client.post(f"{API}/pos/shifts/999999/close", headers=staff_headers, json={"counted_cash": "50.00"})
    assert r.status_code == 404


def test_cash_movement_with_no_open_shift_is_refused(world):
    w = world
    staff_headers = pos_session(w, w.a, w.a.staff)

    r = w.client.post(f"{API}/pos/shifts/1/cash-movement", headers=staff_headers, json={"kind": "PAID_IN", "amount": "5.00", "reason": "Change"})
    assert r.status_code == 400


def test_cash_tender_without_an_open_shift_still_works_with_no_shift_id(world):
    w = world
    staff_headers = pos_session(w, w.a, w.a.staff)
    order_id = ring_cash_order(w, staff_headers)
    payment = w.db.query(Payment).filter_by(order_id=order_id).one()
    assert payment.shift_id is None
    assert w.db.get(Order, order_id).status == OrderStatus.CONFIRMED


def test_admin_shift_list_requires_admin(world):
    w = world
    staff_headers = pos_session(w, w.a, w.a.staff)
    shift_id = w.client.post(f"{API}/pos/shifts/open", headers=staff_headers, json={"starting_float": "50.00"}).json()["shift_id"]
    ring_cash_order(w, staff_headers)
    w.client.post(f"{API}/pos/shifts/{shift_id}/close", headers=staff_headers, json={"counted_cash": "63.20"})

    denied = w.client.get(f"{API}/admin/shifts", params={"restaurant_id": w.a.rid}, headers=header(w.a.staff))
    assert denied.status_code == 403

    allowed = w.client.get(f"{API}/admin/shifts", params={"restaurant_id": w.a.rid}, headers=header(w.a.admin))
    assert allowed.status_code == 200, allowed.text
    rows = allowed.json()
    assert len(rows) == 1
    assert rows[0]["shift_id"] == shift_id
    assert Decimal(rows[0]["variance"]) == Decimal("0.00")
