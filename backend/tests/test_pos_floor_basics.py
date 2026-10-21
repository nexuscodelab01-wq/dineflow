"""Everyday till features: modifiers on a counter sale, 86'ing a dish, customer lookup + loyalty ownership,
coupons at the till and the mid-shift X-report."""

from decimal import Decimal

import pytest

from app.db.session import get_db
from app.main import app
from app.models.coupon import Coupon
from app.models.enums import CouponDiscountType
from app.models.order import Order
from app.models.restaurant_user import RestaurantUser
from app.services.feature_service import FeatureService
from tests.conftest import override_get_db
from tests.tenants import header, make_tenant

API = "/api/v1"


@pytest.fixture
def world(client, db):
    app.dependency_overrides[get_db] = override_get_db(db)
    a = make_tenant(db, "Alpha")
    for flag in ("pos", "coupons"):
        FeatureService(db).set(a.rid, flag, True, None, actor_label="test")
    yield type("W", (), {"client": client, "db": db, "a": a})
    app.dependency_overrides.clear()


def staff_headers(w, tenant=None, user=None, pin="1234"):
    tenant = tenant or w.a
    user = user or tenant.staff
    mid = w.db.query(RestaurantUser).filter_by(restaurant_id=tenant.rid, user_id=user.id).one().id
    w.client.post(f"{API}/admin/devices/staff/{mid}/pin", params={"restaurant_id": tenant.rid}, headers=header(tenant.admin), json={"pin": pin})
    token = w.client.post(f"{API}/admin/devices", params={"restaurant_id": tenant.rid}, headers=header(tenant.admin), json={"label": "Till"}).json()["device_token"]
    login = w.client.post(f"{API}/pos/auth/pin-login", headers={"Authorization": f"Bearer {token}"}, json={"pin": pin}).json()
    return {"Authorization": f"Bearer {login['pos_session_token']}"}


def counter(w, headers, **extra):
    body = {"items": [{"menu_item_id": w.a.item.id, "quantity": 1, "modifier_option_ids": []}], **extra}
    return w.client.post(f"{API}/pos/orders", headers=headers, json=body)


# ---------------------------------------------------------------- modifiers

def test_the_menu_says_which_dishes_have_modifiers(world):
    w = world
    items = w.client.get(f"{API}/menu", params={"restaurant_id": w.a.rid}).json()["items"]
    assert items[0]["has_modifiers"] is True  # the tenant's burger has a Size modifier


def test_a_counter_sale_can_carry_modifiers_and_prices_them(world):
    w = world
    h = staff_headers(w)
    detail = w.client.get(f"{API}/menu/{w.a.item.id}", params={"restaurant_id": w.a.rid}).json()
    option = detail["modifiers"][0]["options"][0]
    r = w.client.post(f"{API}/pos/orders", headers=h, json={"items": [{"menu_item_id": w.a.item.id, "quantity": 1, "modifier_option_ids": [option["id"]]}]})
    assert r.status_code == 201, r.text
    assert r.json()["total"] == "15.40"  # (12.00 + 2.00 Large) + 10%
    assert [m.option_name for m in w.db.get(Order, r.json()["order_id"]).items[0].modifiers] == [option["name"]]


# ---------------------------------------------------------------- 86

def test_86ing_a_dish_from_the_till_hides_it_and_blocks_new_sales(world):
    w = world
    h = staff_headers(w)
    off = w.client.post(f"{API}/pos/menu-items/{w.a.item.id}/availability", headers=h, json={"is_available": False})
    assert off.status_code == 200 and off.json()["is_available"] is False
    assert w.client.get(f"{API}/menu", params={"restaurant_id": w.a.rid}).json()["items"] == []  # gone from the public menu
    till_menu = w.client.get(f"{API}/pos/menu", headers=h).json()["items"]
    assert till_menu[0]["is_available"] is False  # but the till still lists it, so it can be brought back
    assert counter(w, h).status_code == 400
    assert w.client.post(f"{API}/pos/menu-items/{w.a.item.id}/availability", headers=h, json={"is_available": True}).status_code == 200
    assert counter(w, h).status_code == 201


def test_a_till_cannot_86_another_restaurants_dish(world):
    w = world
    b = make_tenant(w.db, "Bravo")
    h = staff_headers(w)
    assert w.client.post(f"{API}/pos/menu-items/{b.item.id}/availability", headers=h, json={"is_available": False}).status_code == 404


# ---------------------------------------------------------------- customers

def test_customer_lookup_finds_this_restaurants_customers_only(world):
    w = world
    b = make_tenant(w.db, "Bravo")
    h = staff_headers(w)
    found = w.client.get(f"{API}/pos/customers", params={"q": "alpha"}, headers=h).json()
    assert [c["id"] for c in found] == [w.a.customer.id]
    assert w.client.get(f"{API}/pos/customers", params={"q": "bravo"}, headers=h).json() == []
    assert b.customer.id not in [c["id"] for c in w.client.get(f"{API}/pos/customers", params={"q": "iso-demo"}, headers=h).json()]
    assert w.client.get(f"{API}/pos/customers", params={"q": "a"}, headers=h).json() == []  # too short to be useful


def test_a_sale_attached_to_a_customer_belongs_to_them(world):
    w = world
    h = staff_headers(w)
    r = counter(w, h, customer_id=w.a.customer.id)
    assert r.status_code == 201, r.text
    order = w.db.get(Order, r.json()["order_id"])
    assert order.user_id == w.a.customer.id and order.customer_email == w.a.customer.email
    # …and without one it is still the staff member's, as before.
    assert w.db.get(Order, counter(w, h).json()["order_id"]).user_id == w.a.staff.id


def test_you_cannot_attach_another_restaurants_customer(world):
    w = world
    b = make_tenant(w.db, "Bravo")
    assert counter(w, staff_headers(w), customer_id=b.customer.id).status_code == 404


# ---------------------------------------------------------------- coupons

def make_coupon(w, code="SAVE25"):
    w.db.add(Coupon(restaurant_id=w.a.rid, code=code, discount_type=CouponDiscountType.PERCENT, discount_value=Decimal("25"), is_active=True))
    w.db.commit()


def test_a_coupon_can_be_previewed_and_applied_at_the_till(world):
    w = world
    make_coupon(w)
    h = staff_headers(w)
    preview = w.client.post(f"{API}/pos/coupons/preview", headers=h, json={"code": "save25", "subtotal": "12.00"})
    assert preview.status_code == 200 and preview.json()["discount"] == "3.00"
    r = counter(w, h, coupon_code="SAVE25")
    assert r.status_code == 201, r.text
    assert r.json()["total"] == "9.90"  # 12.00 − 3.00 = 9.00, + 10% tax
    assert w.db.get(Order, r.json()["order_id"]).discount == Decimal("3.00")


def test_a_bad_coupon_or_a_switched_off_flag_is_refused(world):
    w = world
    make_coupon(w)
    h = staff_headers(w)
    assert counter(w, h, coupon_code="NOPE").status_code == 400
    FeatureService(w.db).set(w.a.rid, "coupons", False, None, actor_label="test")
    w.db.commit()
    assert counter(w, h, coupon_code="SAVE25").status_code == 400


# ---------------------------------------------------------------- x-report

def test_the_x_report_reads_the_till_without_closing_it(world):
    w = world
    h = staff_headers(w)
    assert w.client.get(f"{API}/pos/shifts/current/report", headers=h).status_code == 400  # no open shift
    shift = w.client.post(f"{API}/pos/shifts/open", headers=h, json={"starting_float": "50.00"}).json()["shift_id"]
    order = counter(w, h).json()
    w.client.post(f"{API}/pos/orders/{order['order_id']}/pay-cash", headers=h)
    x = w.client.get(f"{API}/pos/shifts/current/report", headers=h)
    assert x.status_code == 200, x.text
    assert Decimal(x.json()["cash_total"]) == Decimal("13.20") and Decimal(x.json()["expected_cash"]) == Decimal("63.20")
    assert x.json()["closed_at"] is None
    # Still open: it can be read again and then closed for real.
    assert w.client.get(f"{API}/pos/shifts/current/report", headers=h).status_code == 200
    assert w.client.post(f"{API}/pos/shifts/{shift}/close", headers=h, json={"counted_cash": "63.20"}).status_code == 200
