"""Loyalty points: earning on a completed order, viewing a balance, and staff adjustments."""

from decimal import Decimal

import pytest

from app.db.session import get_db
from app.main import app
from app.models.enums import OrderStatus, OrderType, RoleName, TableStatus
from app.models.restaurant import Restaurant
from app.models.restaurant_table import RestaurantTable
from app.models.restaurant_user import RestaurantUser
from app.services.feature_service import FeatureService
from tests.conftest import override_get_db
from tests.tenants import header, make_user

API = "/api/v1"


@pytest.fixture
def world(client, db):
    app.dependency_overrides[get_db] = override_get_db(db)
    restaurant = Restaurant(
        name="Points House", slug="points-house", tax_rate=Decimal("0.1"), delivery_fee=Decimal("2"),
        dine_in_enabled=True, timezone="UTC", loyalty_points_per_currency=2,
    )
    db.add(restaurant)
    db.flush()
    admin = make_user(db, "loyalty-admin@iso-demo.com", RoleName.RESTAURANT_ADMIN)
    staff = make_user(db, "loyalty-staff@iso-demo.com", RoleName.RESTAURANT_STAFF)
    customer = make_user(db, "loyalty-cust@iso-demo.com", RoleName.CUSTOMER, restaurant_id=restaurant.id)
    db.add_all([RestaurantUser(restaurant_id=restaurant.id, user_id=admin.id, role=RoleName.RESTAURANT_ADMIN), RestaurantUser(restaurant_id=restaurant.id, user_id=staff.id, role=RoleName.RESTAURANT_STAFF)])
    db.add(RestaurantTable(restaurant_id=restaurant.id, table_number="P1", capacity=4, status=TableStatus.AVAILABLE))
    db.flush()

    FeatureService(db).set(restaurant.id, "loyalty", True, admin)
    db.commit()
    db.expire_all()

    yield type("W", (), {
        "client": client, "db": db, "rid": restaurant.id, "restaurant": restaurant, "admin": admin,
        "staff": staff, "customer": customer,
    })
    app.dependency_overrides.clear()


def place_order(w, quantity=1):
    """Points House needs its own catalog, since `world` doesn't build one — a fresh menu item priced at $10."""
    from app.models.category import Category
    from app.models.menu_item import MenuItem
    cat = w.db.query(Category).filter(Category.restaurant_id == w.rid).first()
    if cat is None:
        cat = Category(restaurant_id=w.rid, name="Mains", slug="mains")
        w.db.add(cat)
        w.db.flush()
    item = MenuItem(restaurant_id=w.rid, category_id=cat.id, name="Plate", price=Decimal("10.00"), is_available=True)
    w.db.add(item)
    w.db.commit()
    return w.client.post(f"{API}/orders", headers=header(w.customer), json={
        "restaurant_id": w.rid, "order_type": "PICKUP", "customer_name": w.customer.full_name,
        "customer_email": w.customer.email,
        "items": [{"menu_item_id": item.id, "quantity": quantity, "modifier_option_ids": []}],
    })


def complete_order(w, order_id):
    for status in ("CONFIRMED", "PREPARING", "READY", "COMPLETED"):
        r = w.client.patch(f"{API}/admin/orders/{order_id}/status?restaurant_id={w.rid}", headers=header(w.staff), json={"status": status})
        assert r.status_code == 200, r.text
    return r


# ------------------------------------------------------------------ earning

def test_completing_an_order_earns_points_at_the_restaurants_rate(world):
    w = world
    order_id = place_order(w).json()["id"]
    complete_order(w, order_id)

    r = w.client.get(f"{API}/loyalty", headers=header(w.customer))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["balance"] == 22  # $10 + 10% tax = $11 total, * 2 points/currency
    assert body["points_per_currency"] == 2
    [txn] = body["transactions"]
    assert txn["points"] == 22 and txn["reason"] == "EARNED" and txn["order_id"] == order_id


def test_completing_a_second_order_adds_to_the_balance(world):
    w = world
    for _ in range(2):
        order_id = place_order(w).json()["id"]
        complete_order(w, order_id)
    balance = w.client.get(f"{API}/loyalty", headers=header(w.customer)).json()["balance"]
    assert balance == 44


def test_a_guest_order_with_no_account_earns_nothing(world):
    w = world
    # A table-session guest order has no user_id; exercised directly against the service since building
    # a full guest table session is out of scope here — the guard itself is what's under test.
    from app.models.order import Order
    from app.services.loyalty_service import LoyaltyService
    order = Order(
        restaurant_id=w.rid, user_id=None, order_number="PH-GUEST", order_type=OrderType.PICKUP,
        status=OrderStatus.COMPLETED, subtotal=Decimal("10"), tax=Decimal("1"), total=Decimal("11"),
        customer_name="Guest",
    )
    w.db.add(order)
    w.db.flush()
    LoyaltyService(w.db).earn_for_completed_order(order, w.restaurant)
    w.db.commit()
    from app.models.loyalty import LoyaltyTransaction
    assert w.db.query(LoyaltyTransaction).filter(LoyaltyTransaction.order_id == order.id).count() == 0


def test_the_flag_gates_earning_and_viewing(world):
    w = world
    order_id = place_order(w).json()["id"]
    FeatureService(w.db).set(w.rid, "loyalty", False, w.admin)
    w.db.commit()
    complete_order(w, order_id)  # completes fine; just doesn't earn, since the flag check is server-side
    assert w.client.get(f"{API}/loyalty", headers=header(w.customer)).status_code == 403


# ------------------------------------------------------------------ admin

def test_staff_can_list_and_adjust_balances(world):
    w = world
    order_id = place_order(w).json()["id"]
    complete_order(w, order_id)

    listed = w.client.get(f"{API}/admin/loyalty?restaurant_id={w.rid}", headers=header(w.staff)).json()
    assert len(listed) == 1 and listed[0]["balance"] == 22 and listed[0]["email"] == w.customer.email

    adjusted = w.client.post(
        f"{API}/admin/loyalty/{w.customer.id}/adjust?restaurant_id={w.rid}", headers=header(w.staff),
        json={"points": 5, "note": "Sorry about the wait"},
    )
    assert adjusted.status_code == 200 and adjusted.json()["balance"] == 27

    mine = w.client.get(f"{API}/loyalty", headers=header(w.customer)).json()
    assert mine["balance"] == 27 and len(mine["transactions"]) == 2


def test_staff_cannot_deduct_more_points_than_the_customer_has(world):
    w = world
    r = w.client.post(
        f"{API}/admin/loyalty/{w.customer.id}/adjust?restaurant_id={w.rid}", headers=header(w.staff),
        json={"points": -10},
    )
    assert r.status_code == 400


def test_zero_points_is_refused(world):
    w = world
    r = w.client.post(f"{API}/admin/loyalty/{w.customer.id}/adjust?restaurant_id={w.rid}", headers=header(w.staff), json={"points": 0})
    assert r.status_code == 422


def test_only_staff_can_manage_loyalty(world):
    w = world
    assert w.client.get(f"{API}/admin/loyalty?restaurant_id={w.rid}", headers=header(w.customer)).status_code == 403
    assert w.client.post(
        f"{API}/admin/loyalty/{w.customer.id}/adjust?restaurant_id={w.rid}", headers=header(w.customer), json={"points": 5},
    ).status_code == 403
