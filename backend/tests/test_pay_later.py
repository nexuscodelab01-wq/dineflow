"""Pay at pickup / cash on delivery: kitchen first, money later — with the rules that protect against no-shows."""

from decimal import Decimal

import pytest
import stripe

from app.api.routes.webhooks import _handle_payment_succeeded
from app.db.session import get_db
from app.main import app
from app.models.enums import OrderStatus, PaymentMethod, PaymentStatus
from app.models.order import Order
from app.models.payment import Payment
from app.models.restaurant import Restaurant
from app.models.restaurant_user import RestaurantUser
from app.services.feature_service import FeatureService
from tests.conftest import override_get_db
from tests.tenants import header, make_tenant, place_order

API = "/api/v1"


@pytest.fixture
def world(client, db):
    app.dependency_overrides[get_db] = override_get_db(db)
    a = make_tenant(db, "Alpha")
    for flag in ("pos", "pay_later"):
        FeatureService(db).set(a.rid, flag, True, None, actor_label="test")
    r = db.get(Restaurant, a.rid)
    r.pay_at_pickup_enabled = r.cash_on_delivery_enabled = True
    db.commit()
    yield type("W", (), {"client": client, "db": db, "a": a})
    app.dependency_overrides.clear()


def customer_with_a_paid_order(w):
    """Pay-later is for returning customers: give this one a normal paid order first."""
    assert place_order(w.client, w.a).status_code == 201


def later(w, order_type="PICKUP", phone="555-0100", qty=1, **extra):
    body = {
        "restaurant_id": w.a.rid, "order_type": order_type, "customer_name": "Pat", "customer_email": w.a.customer.email,
        "customer_phone": phone, "pay_later": True, "items": [{"menu_item_id": w.a.item.id, "quantity": qty, "modifier_option_ids": []}], **extra,
    }
    if order_type == "DELIVERY":
        body["delivery_address"] = {"street": "1 Main", "city": "Town", "postal_code": "12345"}
    return w.client.post(f"{API}/orders", headers=header(w.a.customer), json=body)


def till(w, pin="1234"):
    mid = w.db.query(RestaurantUser).filter_by(restaurant_id=w.a.rid, user_id=w.a.staff.id).one().id
    w.client.post(f"{API}/admin/devices/staff/{mid}/pin", params={"restaurant_id": w.a.rid}, headers=header(w.a.admin), json={"pin": pin})
    token = w.client.post(f"{API}/admin/devices", params={"restaurant_id": w.a.rid}, headers=header(w.a.admin), json={"label": "Till"}).json()["device_token"]
    login = w.client.post(f"{API}/pos/auth/pin-login", headers={"Authorization": f"Bearer {token}"}, json={"pin": pin}).json()
    return {"Authorization": f"Bearer {login['pos_session_token']}"}


# ---------------------------------------------------------------- placing

def test_a_returning_customer_can_pay_at_pickup_and_the_kitchen_gets_it_now(world):
    w = world
    customer_with_a_paid_order(w)
    r = later(w)
    assert r.status_code == 201, r.text
    order = w.db.get(Order, r.json()["id"])
    assert order.pay_later and order.status == OrderStatus.CONFIRMED
    payment = w.db.query(Payment).filter_by(order_id=order.id).one()
    assert payment.status == PaymentStatus.PENDING and payment.amount == order.total
    assert r.json()["client_secret"] is None  # nothing to pay online


def test_a_first_order_must_be_paid_online(world):
    r = later(world)
    assert r.status_code == 400 and "first order" in r.json()["detail"]


def test_the_first_order_rule_can_be_switched_off(world):
    w = world
    w.db.get(Restaurant, w.a.rid).pay_later_first_order_prepaid = False
    w.db.commit()
    assert later(w).status_code == 201


def test_pay_later_has_guard_rails(world):
    w = world
    customer_with_a_paid_order(w)
    assert later(w, phone="").status_code == 400                      # a way to reach them
    assert later(w, qty=20).status_code == 400                         # over the cap (12.00 × 20 > 100)
    assert later(w, order_type="DINE_IN", reservation_id=w.a.reservation.id).status_code == 400  # tabs are paid at the end already
    assert later(w).status_code == 201 and later(w).status_code == 201
    assert later(w).status_code == 400                                 # two unpaid at a time


def test_each_order_type_needs_its_own_switch(world):
    w = world
    customer_with_a_paid_order(w)
    w.db.get(Restaurant, w.a.rid).cash_on_delivery_enabled = False
    w.db.commit()
    assert later(w, order_type="DELIVERY").status_code == 400
    assert later(w).status_code == 201


def test_pay_later_needs_the_flag(world):
    w = world
    customer_with_a_paid_order(w)
    FeatureService(w.db).set(w.a.rid, "pay_later", False, None, actor_label="test")
    w.db.commit()
    assert later(w).status_code == 400


# ---------------------------------------------------------------- taking the money

def test_the_till_lists_unpaid_orders_and_takes_cash(world):
    w = world
    customer_with_a_paid_order(w)
    order_id = later(w).json()["id"]
    h = till(w)
    shift = w.client.post(f"{API}/pos/shifts/open", headers=h, json={"starting_float": "50.00"}).json()["shift_id"]
    waiting = w.client.get(f"{API}/pos/orders/awaiting-payment", headers=h).json()
    assert [o["order_id"] for o in waiting] == [order_id] and waiting[0]["customer_phone"] == "555-0100"
    assert w.client.post(f"{API}/pos/orders/{order_id}/pay-cash", headers=h).status_code == 204
    payment = w.db.query(Payment).filter_by(order_id=order_id).one()
    assert payment.status == PaymentStatus.COMPLETED and payment.payment_method == PaymentMethod.CASH
    assert payment.staff_user_id == w.a.staff.id and payment.shift_id == shift
    assert w.client.get(f"{API}/pos/orders/awaiting-payment", headers=h).json() == []
    assert w.client.post(f"{API}/pos/orders/{order_id}/pay-cash", headers=h).status_code == 400  # not twice
    z = w.client.post(f"{API}/pos/shifts/{shift}/close", headers=h, json={"counted_cash": "63.20"}).json()
    assert Decimal(z["cash_total"]) == Decimal("13.20") and Decimal(z["variance"]) == Decimal("0.00")


def test_the_till_can_take_a_card_for_it_too(world):
    w = world
    customer_with_a_paid_order(w)
    order_id = later(w).json()["id"]
    h = till(w)
    r = w.client.post(f"{API}/pos/orders/{order_id}/pay-card", headers=h)
    assert r.status_code == 200, r.text
    payment = w.db.query(Payment).filter_by(order_id=order_id).one()
    assert payment.status == PaymentStatus.COMPLETED and payment.payment_method == PaymentMethod.CARD
    assert w.db.query(Payment).filter_by(order_id=order_id).count() == 1  # the waiting row was reused, not duplicated


def test_a_card_confirmed_later_by_the_webhook_settles_it_without_touching_the_order(world):
    w = world
    customer_with_a_paid_order(w)
    order_id = later(w).json()["id"]
    payment = w.db.query(Payment).filter_by(order_id=order_id).one()
    payment.provider_intent_id, payment.payment_method, payment.staff_user_id = "pi_later", PaymentMethod.CARD, w.a.staff.id
    w.db.commit()
    _handle_payment_succeeded(w.db, stripe.StripeObject.construct_from({"id": "pi_later"}, "sk"))
    w.db.refresh(payment)
    assert payment.status == PaymentStatus.COMPLETED
    assert w.db.get(Order, order_id).status == OrderStatus.CONFIRMED


def test_an_admin_can_record_cash_without_a_till(world):
    w = world
    customer_with_a_paid_order(w)
    order_id = later(w, order_type="DELIVERY").json()["id"]
    r = w.client.post(f"{API}/admin/orders/{order_id}/mark-paid", params={"restaurant_id": w.a.rid}, headers=header(w.a.admin))
    assert r.status_code == 204, r.text
    assert w.db.query(Payment).filter_by(order_id=order_id).one().status == PaymentStatus.COMPLETED
    assert w.client.post(f"{API}/admin/orders/{order_id}/mark-paid", params={"restaurant_id": w.a.rid}, headers=header(w.a.admin)).status_code == 400


def test_cancelling_an_unpaid_pay_later_order_closes_its_waiting_payment(world):
    w = world
    customer_with_a_paid_order(w)
    order_id = later(w).json()["id"]
    r = w.client.patch(f"{API}/admin/orders/{order_id}/status", params={"restaurant_id": w.a.rid}, headers=header(w.a.admin), json={"status": "CANCELLED"})
    assert r.status_code == 200, r.text
    assert w.db.query(Payment).filter_by(order_id=order_id).one().status == PaymentStatus.FAILED
    h = till(w)
    assert w.client.get(f"{API}/pos/orders/awaiting-payment", headers=h).json() == []


def test_another_restaurants_till_cannot_settle_it(world):
    w = world
    customer_with_a_paid_order(w)
    order_id = later(w).json()["id"]
    b = make_tenant(w.db, "Bravo")
    FeatureService(w.db).set(b.rid, "pos", True, None, actor_label="test")
    mid = w.db.query(RestaurantUser).filter_by(restaurant_id=b.rid, user_id=b.staff.id).one().id
    w.client.post(f"{API}/admin/devices/staff/{mid}/pin", params={"restaurant_id": b.rid}, headers=header(b.admin), json={"pin": "4321"})
    token = w.client.post(f"{API}/admin/devices", params={"restaurant_id": b.rid}, headers=header(b.admin), json={"label": "Till"}).json()["device_token"]
    login = w.client.post(f"{API}/pos/auth/pin-login", headers={"Authorization": f"Bearer {token}"}, json={"pin": "4321"}).json()
    theirs = {"Authorization": f"Bearer {login['pos_session_token']}"}
    assert w.client.post(f"{API}/pos/orders/{order_id}/pay-cash", headers=theirs).status_code == 404
    assert w.client.get(f"{API}/pos/orders/awaiting-payment", headers=theirs).json() == []
    assert w.db.query(Payment).filter_by(order_id=order_id).one().status == PaymentStatus.PENDING


def test_settings_can_switch_it_on_only_with_the_flag(world):
    w = world
    FeatureService(w.db).set(w.a.rid, "pay_later", False, None, actor_label="test")
    w.db.commit()
    r = w.client.patch(f"{API}/admin/settings", params={"restaurant_id": w.a.rid}, headers=header(w.a.admin), json={"pay_at_pickup_enabled": True})
    assert r.status_code == 400
