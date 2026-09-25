"""Discount coupons: the rules, the money, and that the client can never set the amount."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.db.session import get_db
from app.main import app
from app.models.category import Category
from app.models.coupon import Coupon, CouponRedemption
from app.models.enums import CouponDiscountType, RoleName
from app.models.menu_item import MenuItem
from app.models.restaurant import Restaurant
from app.models.restaurant_user import RestaurantUser
from app.services.feature_service import FeatureService
from tests.conftest import override_get_db
from tests.tenants import header, make_user

API = "/api/v1"


@pytest.fixture
def world(client, db):
    app.dependency_overrides[get_db] = override_get_db(db)
    restaurant = Restaurant(
        name="Coupon Cafe", slug="coupon-cafe", tax_rate=Decimal("0.10"), delivery_fee=Decimal("2"),
        pickup_enabled=True, timezone="UTC",
    )
    db.add(restaurant)
    db.flush()
    admin = make_user(db, "coupon-admin@iso-demo.com", RoleName.RESTAURANT_ADMIN)
    staff = make_user(db, "coupon-staff@iso-demo.com", RoleName.RESTAURANT_STAFF)
    customer = make_user(db, "coupon-cust@iso-demo.com", RoleName.CUSTOMER, restaurant_id=restaurant.id)
    other = make_user(db, "coupon-other@iso-demo.com", RoleName.CUSTOMER, restaurant_id=restaurant.id)
    db.add_all([
        RestaurantUser(restaurant_id=restaurant.id, user_id=admin.id, role=RoleName.RESTAURANT_ADMIN),
        RestaurantUser(restaurant_id=restaurant.id, user_id=staff.id, role=RoleName.RESTAURANT_STAFF),
    ])
    category = Category(restaurant_id=restaurant.id, name="Mains", slug="mains")
    db.add(category)
    db.flush()
    item = MenuItem(restaurant_id=restaurant.id, category_id=category.id, name="Plate", price=Decimal("10.00"), is_available=True)
    db.add(item)
    db.flush()

    FeatureService(db).set(restaurant.id, "coupons", True, admin)
    db.commit()
    db.expire_all()

    yield type("W", (), {
        "client": client, "db": db, "rid": restaurant.id, "restaurant": restaurant, "admin": admin,
        "staff": staff, "customer": customer, "other": other, "item": item,
    })
    app.dependency_overrides.clear()


def make_coupon(w, code="SAVE25", **fields):
    values = {
        "restaurant_id": w.rid, "code": code, "discount_type": CouponDiscountType.PERCENT,
        "discount_value": Decimal("25.00"), **fields,
    }
    coupon = Coupon(**values)
    w.db.add(coupon)
    w.db.commit()
    w.db.refresh(coupon)
    return coupon


def order(w, *, code=None, quantity=2, user=None, extra=None):
    """A $10 plate x2 = $20.00 subtotal, 10% tax."""
    body = {
        "restaurant_id": w.rid, "order_type": "PICKUP", "customer_name": "Coupon Customer",
        "customer_email": (user or w.customer).email,
        "items": [{"menu_item_id": w.item.id, "quantity": quantity, "modifier_option_ids": []}],
    }
    if code is not None:
        body["coupon_code"] = code
    if extra:
        body.update(extra)
    return w.client.post(f"{API}/orders", headers=header(user or w.customer), json=body)


# ------------------------------------------------------------------ the money

def test_a_percentage_coupon_comes_off_before_tax(world):
    w = world
    make_coupon(w, "SAVE25", discount_type=CouponDiscountType.PERCENT, discount_value=Decimal("25"))
    r = order(w, code="SAVE25")
    assert r.status_code == 201, r.text
    body = r.json()
    assert Decimal(body["subtotal"]) == Decimal("20.00")
    assert Decimal(body["discount"]) == Decimal("5.00")
    assert Decimal(body["tax"]) == Decimal("1.50")    # 10% of the discounted 15.00, not of 20.00
    assert Decimal(body["total"]) == Decimal("16.50")


def test_a_fixed_coupon_takes_its_amount_off(world):
    w = world
    make_coupon(w, "FIVEOFF", discount_type=CouponDiscountType.FIXED, discount_value=Decimal("5.00"))
    body = order(w, code="FIVEOFF").json()
    assert Decimal(body["discount"]) == Decimal("5.00")
    assert Decimal(body["total"]) == Decimal("16.50")


def test_a_percentage_coupon_is_capped_by_max_discount_amount(world):
    w = world
    make_coupon(w, "HALF", discount_value=Decimal("50"), max_discount_amount=Decimal("3.00"))
    body = order(w, code="HALF").json()
    assert Decimal(body["discount"]) == Decimal("3.00")  # 50% of 20 is 10, capped at 3


def test_a_discount_never_exceeds_the_subtotal(world):
    w = world
    make_coupon(w, "HUGE", discount_type=CouponDiscountType.FIXED, discount_value=Decimal("500.00"))
    body = order(w, code="HUGE").json()
    assert Decimal(body["discount"]) == Decimal("20.00")
    assert Decimal(body["total"]) == Decimal("0.00")  # free, never negative


def test_the_code_is_case_and_space_insensitive(world):
    w = world
    make_coupon(w, "SAVE25")
    body = order(w, code="  save25 ").json()
    assert Decimal(body["discount"]) == Decimal("5.00")


# ------------------------------------------------------------------ the client never sets the amount

def test_a_client_supplied_discount_is_ignored(world):
    w = world
    r = order(w, extra={"discount": "19.99", "subtotal": "0.01", "total": "0.01"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert Decimal(body["discount"]) == Decimal("0.00")
    assert Decimal(body["total"]) == Decimal("22.00")  # 20 + 10% tax, exactly as if nothing was sent


def test_an_unknown_code_is_refused_rather_than_silently_charged_in_full(world):
    w = world
    r = order(w, code="NOSUCHCODE")
    assert r.status_code == 400
    assert "valid" in r.json()["detail"].lower()


# ------------------------------------------------------------------ the rules

def test_an_inactive_coupon_is_refused(world):
    w = world
    make_coupon(w, "OFF", is_active=False)
    assert order(w, code="OFF").status_code == 400


def test_a_coupon_outside_its_dates_is_refused(world):
    w = world
    now = datetime.now(UTC)
    make_coupon(w, "EXPIRED", ends_at=now - timedelta(days=1))
    make_coupon(w, "FUTURE", starts_at=now + timedelta(days=1))
    assert "expired" in order(w, code="EXPIRED").json()["detail"].lower()
    assert "yet" in order(w, code="FUTURE").json()["detail"].lower()


def test_a_coupon_below_its_minimum_order_is_refused(world):
    w = world
    make_coupon(w, "BIGSPEND", min_order_amount=Decimal("50.00"))
    r = order(w, code="BIGSPEND")  # subtotal is only 20.00
    assert r.status_code == 400 and "at least" in r.json()["detail"].lower()


def test_a_fully_claimed_coupon_is_refused(world):
    w = world
    make_coupon(w, "FIRSTONE", max_redemptions=1)
    assert order(w, code="FIRSTONE").status_code == 201
    second = order(w, code="FIRSTONE", user=w.other)
    assert second.status_code == 400 and "claimed" in second.json()["detail"].lower()


def test_a_customer_cannot_use_a_once_per_customer_coupon_twice(world):
    w = world
    make_coupon(w, "ONCE", max_per_customer=1)
    assert order(w, code="ONCE").status_code == 201
    again = order(w, code="ONCE")
    assert again.status_code == 400 and "already used" in again.json()["detail"].lower()
    # ...but it's still there for somebody else
    assert order(w, code="ONCE", user=w.other).status_code == 201


def test_redeeming_records_a_ledger_row_and_bumps_the_count(world):
    w = world
    coupon = make_coupon(w, "SAVE25")
    order_id = order(w, code="SAVE25").json()["id"]

    w.db.expire_all()
    redemption = w.db.query(CouponRedemption).filter(CouponRedemption.order_id == order_id).one()
    assert redemption.coupon_id == coupon.id
    assert redemption.user_id == w.customer.id
    assert redemption.amount == Decimal("5.00")
    assert w.db.get(Coupon, coupon.id).times_redeemed == 1


def test_the_flag_gates_coupons(world):
    w = world
    make_coupon(w, "SAVE25")
    FeatureService(w.db).set(w.rid, "coupons", False, w.admin)
    w.db.commit()
    r = order(w, code="SAVE25")
    assert r.status_code == 400 and "not available" in r.json()["detail"].lower()
    # an order without a code still goes through untouched
    assert order(w).status_code == 201


# ------------------------------------------------------------------ preview

def test_preview_shows_what_a_code_is_worth(world):
    w = world
    make_coupon(w, "SAVE25", description="25% off")
    r = w.client.post(f"{API}/coupons/preview", headers=header(w.customer), json={"code": "save25", "subtotal": "20.00"})
    assert r.status_code == 200, r.text
    assert r.json() == {"code": "SAVE25", "description": "25% off", "discount": "5.00"}


def test_preview_refuses_a_code_that_would_not_apply(world):
    w = world
    make_coupon(w, "BIGSPEND", min_order_amount=Decimal("50.00"))
    r = w.client.post(f"{API}/coupons/preview", headers=header(w.customer), json={"code": "BIGSPEND", "subtotal": "20.00"})
    assert r.status_code == 400


# ------------------------------------------------------------------ staff CRUD

def test_an_admin_can_create_list_and_update_a_coupon(world):
    w = world
    created = w.client.post(f"{API}/admin/coupons?restaurant_id={w.rid}", headers=header(w.admin), json={
        "code": "welcome10", "description": "Welcome", "discount_type": "PERCENT", "discount_value": "10",
    })
    assert created.status_code == 201, created.text
    assert created.json()["code"] == "WELCOME10"  # normalized

    listed = w.client.get(f"{API}/admin/coupons?restaurant_id={w.rid}", headers=header(w.staff)).json()
    assert [c["code"] for c in listed] == ["WELCOME10"]

    updated = w.client.patch(
        f"{API}/admin/coupons/{created.json()['id']}?restaurant_id={w.rid}", headers=header(w.admin),
        json={"is_active": False},
    )
    assert updated.status_code == 200 and updated.json()["is_active"] is False


def test_a_duplicate_code_is_refused(world):
    w = world
    make_coupon(w, "SAVE25")
    r = w.client.post(f"{API}/admin/coupons?restaurant_id={w.rid}", headers=header(w.admin), json={
        "code": "save25", "discount_type": "FIXED", "discount_value": "2",
    })
    assert r.status_code == 409


def test_a_percentage_over_100_is_refused(world):
    w = world
    r = w.client.post(f"{API}/admin/coupons?restaurant_id={w.rid}", headers=header(w.admin), json={
        "code": "TOOMUCH", "discount_type": "PERCENT", "discount_value": "150",
    })
    assert r.status_code == 422


def test_deleting_a_used_coupon_deactivates_it_so_past_orders_keep_their_history(world):
    w = world
    coupon = make_coupon(w, "SAVE25")
    order(w, code="SAVE25")

    r = w.client.delete(f"{API}/admin/coupons/{coupon.id}?restaurant_id={w.rid}", headers=header(w.admin))
    assert r.status_code == 204
    w.db.expire_all()
    still_there = w.db.get(Coupon, coupon.id)
    assert still_there is not None and still_there.is_active is False


def test_deleting_an_unused_coupon_removes_it(world):
    w = world
    coupon = make_coupon(w, "NEVERUSED")
    assert w.client.delete(f"{API}/admin/coupons/{coupon.id}?restaurant_id={w.rid}", headers=header(w.admin)).status_code == 204
    w.db.expire_all()
    assert w.db.get(Coupon, coupon.id) is None


def test_only_staff_can_manage_coupons(world):
    w = world
    coupon = make_coupon(w, "SAVE25")
    assert w.client.get(f"{API}/admin/coupons?restaurant_id={w.rid}", headers=header(w.customer)).status_code == 403
    assert w.client.post(f"{API}/admin/coupons?restaurant_id={w.rid}", headers=header(w.customer), json={
        "code": "MINE", "discount_type": "FIXED", "discount_value": "5",
    }).status_code == 403
    assert w.client.delete(f"{API}/admin/coupons/{coupon.id}?restaurant_id={w.rid}", headers=header(w.staff)).status_code == 403
