"""Counter orders from the POS: flag-gated, paid before it hits the kitchen (not after — the normal
quick-service counter pattern, unlike a table's tab), staff attribution."""

from decimal import Decimal

import pytest

from app.db.session import get_db
from app.main import app
from app.models.enums import OrderStatus, OrderType, PaymentStatus
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


def test_a_counter_order_is_created_pending_and_attributed(world):
    """PENDING, not CONFIRMED — it hasn't been paid yet, so it must not be visible to the kitchen or
    counted as revenue until mark_counter_order_paid_cash actually confirms it."""
    w = world
    staff_headers = pos_session(w, w.a, w.a.staff)

    r = w.client.post(f"{API}/pos/orders", headers=staff_headers, json={"items": [{"menu_item_id": w.a.item.id, "quantity": 2, "modifier_option_ids": []}]})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "PENDING"
    assert body["total"] == str((Decimal("12.00") * 2 * Decimal("1.10")).quantize(Decimal("0.01")))

    order = w.db.get(Order, body["order_id"])
    assert order.order_type == OrderType.COUNTER
    assert order.user_id == w.a.staff.id
    assert order.status == OrderStatus.PENDING
    assert order.customer_name == "Alpha (staff)"


def test_cash_tender_is_what_actually_confirms_the_order(world):
    w = world
    staff_headers = pos_session(w, w.a, w.a.staff)
    created = w.client.post(f"{API}/pos/orders", headers=staff_headers, json={"items": [{"menu_item_id": w.a.item.id, "quantity": 1, "modifier_option_ids": []}]})
    order_id = created.json()["order_id"]
    assert w.db.get(Order, order_id).status == OrderStatus.PENDING

    r = w.client.post(f"{API}/pos/orders/{order_id}/pay-cash", headers=staff_headers)
    assert r.status_code == 204, r.text

    order = w.db.get(Order, order_id)
    assert order.status == OrderStatus.CONFIRMED


def test_counter_orders_are_refused_when_the_pos_flag_is_off(world):
    w = world
    FeatureService(w.db).set(w.a.rid, "pos", None, None, actor_label="test")  # back to default (off)
    staff_headers = pos_session(w, w.a, w.a.staff)

    r = w.client.post(f"{API}/pos/orders", headers=staff_headers, json={"items": [{"menu_item_id": w.a.item.id, "quantity": 1, "modifier_option_ids": []}]})
    assert r.status_code == 403


def test_cash_tender_marks_the_order_paid(world):
    w = world
    staff_headers = pos_session(w, w.a, w.a.staff)
    created = w.client.post(f"{API}/pos/orders", headers=staff_headers, json={"items": [{"menu_item_id": w.a.item.id, "quantity": 1, "modifier_option_ids": []}]})
    order_id = created.json()["order_id"]

    r = w.client.post(f"{API}/pos/orders/{order_id}/pay-cash", headers=staff_headers)
    assert r.status_code == 204, r.text

    payment = w.db.query(Payment).filter_by(order_id=order_id).one()
    assert payment.status == PaymentStatus.COMPLETED
    assert payment.payment_method.value == "CASH" and payment.provider == "MANUAL"
    assert payment.staff_user_id == w.a.staff.id


def test_cannot_pay_cash_twice(world):
    w = world
    staff_headers = pos_session(w, w.a, w.a.staff)
    created = w.client.post(f"{API}/pos/orders", headers=staff_headers, json={"items": [{"menu_item_id": w.a.item.id, "quantity": 1, "modifier_option_ids": []}]})
    order_id = created.json()["order_id"]
    w.client.post(f"{API}/pos/orders/{order_id}/pay-cash", headers=staff_headers)

    r = w.client.post(f"{API}/pos/orders/{order_id}/pay-cash", headers=staff_headers)
    assert r.status_code == 400


def test_a_plain_staff_jwt_is_refused_on_pos_routes(world):
    w = world
    r = w.client.post(f"{API}/pos/orders", headers=header(w.a.staff), json={"items": []})
    assert r.status_code == 401
