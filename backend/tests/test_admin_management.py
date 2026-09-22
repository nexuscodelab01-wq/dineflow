"""Admin API: permissions, menu/category/modifier CRUD, orders, kitchen, customers, settings, isolation."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password
from app.db.session import get_db
from app.main import app
from app.models.category import Category
from app.models.enums import ReservationStatus, RoleName, TableStatus
from app.models.menu_item import MenuItem
from app.models.reservation import Reservation
from app.models.restaurant import Restaurant
from app.models.restaurant_table import RestaurantTable
from app.models.restaurant_user import RestaurantUser
from app.models.role import Role
from app.models.user import User
from tests.conftest import override_get_db


def _header(user: User) -> dict[str, str]:
    role = user.role.name.value if hasattr(user.role.name, "value") else str(user.role.name)
    return {"Authorization": f"Bearer {create_access_token(str(user.id), claims={'role': role, 'tenant': user.restaurant_id})}"}


def _user(db: Session, email: str, role: RoleName, first="T", restaurant_id: int | None = None) -> User:
    role_row = db.query(Role).filter(Role.name == role.value).one()
    user = User(email=email, hashed_password=hash_password("Test1234!"), first_name=first, last_name="User", role_id=role_row.id, restaurant_id=restaurant_id)
    db.add(user)
    db.flush()
    return user


@pytest.fixture
def world(client: TestClient, db: Session):
    """Two restaurants (A with admin+staff+customer, B with its own admin) sharing one database."""
    app.dependency_overrides[get_db] = override_get_db(db)
    a = Restaurant(name="Alpha", slug="alpha-am", tax_rate=Decimal("0.10"), delivery_fee=Decimal("2.00"))
    b = Restaurant(name="Bravo", slug="bravo-am", tax_rate=Decimal("0.05"), delivery_fee=Decimal("3.00"))
    db.add_all([a, b])
    db.flush()
    admin = _user(db, "am-admin@demo.com", RoleName.RESTAURANT_ADMIN, "Ada")
    staff = _user(db, "am-staff@demo.com", RoleName.RESTAURANT_STAFF, "Stan")
    customer = _user(db, "am-cust@demo.com", RoleName.CUSTOMER, "Cara", restaurant_id=a.id)
    admin_b = _user(db, "am-admin-b@demo.com", RoleName.RESTAURANT_ADMIN, "Bea")
    db.add_all([
        RestaurantUser(restaurant_id=a.id, user_id=admin.id),
        RestaurantUser(restaurant_id=a.id, user_id=staff.id),
        RestaurantUser(restaurant_id=b.id, user_id=admin_b.id),
    ])
    cat = Category(restaurant_id=a.id, name="Mains", slug="mains")
    db.add(cat)
    db.flush()
    item = MenuItem(restaurant_id=a.id, category_id=cat.id, name="Burger", price=Decimal("12.00"), is_available=True)
    db.add(item)
    db.flush()
    db.expire_all()
    yield type("W", (), {
        "client": client, "db": db, "a": a, "b": b, "cat": cat, "item": item,
        "admin": _header(db.get(User, admin.id)), "staff": _header(db.get(User, staff.id)),
        "customer": _header(db.get(User, customer.id)), "admin_b": _header(db.get(User, admin_b.id)),
        "customer_user": db.get(User, customer.id),
    })
    app.dependency_overrides.clear()


def url(w, path, restaurant=None, **params):
    extra = "".join(f"&{k}={v}" for k, v in params.items())
    return f"/api/v1/admin{path}?restaurant_id={(restaurant or w.a).id}{extra}"


def place_order(w, **extra):
    """A PICKUP order by the customer for two burgers."""
    return w.client.post("/api/v1/orders", headers=w.customer, json={
        "restaurant_id": w.a.id, "order_type": "PICKUP", "customer_name": "Cara User",
        "customer_email": "am-cust@demo.com",
        "items": [{"menu_item_id": w.item.id, "quantity": 2, "modifier_option_ids": []}], **extra,
    })


# ---------------------------------------------------------------- permissions

def test_customers_cannot_use_admin_endpoints(world):
    w = world
    for path in ("/dashboard", "/menu", "/orders", "/kitchen", "/tables", "/customers", "/settings", "/analytics"):
        assert w.client.get(url(w, path), headers=w.customer).status_code == 403, path
    assert w.client.get(url(w, "/dashboard")).status_code == 401           # not signed in at all


def test_staff_can_read_but_not_change_the_menu_or_settings(world):
    w = world
    assert w.client.get(url(w, "/menu"), headers=w.staff).status_code == 200
    assert w.client.get(url(w, "/orders"), headers=w.staff).status_code == 200
    write = w.client.post(url(w, "/menu"), headers=w.staff, json={
        "restaurant_id": w.a.id, "category_id": w.cat.id, "name": "Nope", "price": "5.00"})
    assert write.status_code == 403
    assert w.client.get(url(w, "/settings"), headers=w.staff).status_code == 403
    assert w.client.patch(url(w, "/settings"), headers=w.staff, json={"description": "x"}).status_code == 403
    assert w.client.post(url(w, "/tables"), headers=w.staff, json={"restaurant_id": w.a.id, "table_number": "S1", "capacity": 2}).status_code == 403


def test_admins_are_locked_to_their_own_restaurant(world):
    w = world
    # Bravo's admin can't read, edit or delete Alpha's data — even by guessing ids.
    assert w.client.get(url(w, "/menu"), headers=w.admin_b).status_code == 403
    assert w.client.put(url(w, f"/menu/{w.item.id}"), headers=w.admin_b, json={"name": "Hacked"}).status_code == 403
    assert w.client.delete(url(w, f"/menu/{w.item.id}"), headers=w.admin_b).status_code == 403
    # Using their own restaurant id with Alpha's item id must not work either.
    r = w.client.put(url(w, f"/menu/{w.item.id}", restaurant=w.b), headers=w.admin_b, json={"name": "Hacked"})
    assert r.status_code == 404
    assert w.db.get(MenuItem, w.item.id).name == "Burger"
    # A client can't smuggle another restaurant into a create body.
    bad = w.client.post(url(w, "/categories"), headers=w.admin, json={"restaurant_id": w.b.id, "name": "X", "slug": "x"})
    assert bad.status_code == 400


# ---------------------------------------------------------------- categories & menu

def test_category_crud(world):
    w = world
    made = w.client.post(url(w, "/categories"), headers=w.admin, json={"restaurant_id": w.a.id, "name": "Desserts", "slug": "desserts", "sort_order": 3})
    assert made.status_code == 201, made.text
    cid = made.json()["id"]
    upd = w.client.put(url(w, f"/categories/{cid}"), headers=w.admin, json={"name": "Sweets"})
    assert upd.status_code == 200 and upd.json()["name"] == "Sweets" and upd.json()["slug"] == "desserts"
    assert any(c["id"] == cid for c in w.client.get(url(w, "/categories"), headers=w.staff).json())
    assert w.client.delete(url(w, f"/categories/{cid}"), headers=w.admin).status_code == 204
    assert w.client.put(url(w, f"/categories/{cid}"), headers=w.admin, json={"name": "Gone"}).status_code == 404


def test_duplicate_category_slug_is_a_clean_conflict(world):
    w = world
    r = w.client.post(url(w, "/categories"), headers=w.admin, json={"restaurant_id": w.a.id, "name": "Again", "slug": "mains"})
    assert r.status_code == 409, r.text


def test_deleting_a_category_that_still_has_items_is_refused_cleanly(world):
    w = world
    r = w.client.delete(url(w, f"/categories/{w.cat.id}"), headers=w.admin)
    assert r.status_code == 409 and "menu item" in r.json()["detail"].lower()


def test_reorder_categories(world):
    w = world
    c2 = w.client.post(url(w, "/categories"), headers=w.admin, json={"restaurant_id": w.a.id, "name": "Sides", "slug": "sides", "sort_order": 5}).json()
    r = w.client.patch(url(w, "/categories/reorder"), headers=w.admin, json={"items": [{"id": c2["id"], "sort_order": 0}, {"id": w.cat.id, "sort_order": 1}]})
    assert r.status_code == 200
    assert [c["name"] for c in r.json()][:2] == ["Sides", "Mains"]


def test_menu_item_crud_and_validation(world):
    w = world
    body = {"restaurant_id": w.a.id, "category_id": w.cat.id, "name": "Pasta", "price": "14.50", "is_vegetarian": True}
    made = w.client.post(url(w, "/menu"), headers=w.admin, json=body)
    assert made.status_code == 201, made.text
    iid = made.json()["id"]
    assert made.json()["category_name"] == "Mains" and made.json()["is_vegetarian"] is True

    assert w.client.post(url(w, "/menu"), headers=w.admin, json={**body, "price": "0"}).status_code == 422
    assert w.client.post(url(w, "/menu"), headers=w.admin, json={**body, "name": ""}).status_code == 422
    assert w.client.post(url(w, "/menu"), headers=w.admin, json={**body, "category_id": 999999}).status_code == 404

    upd = w.client.put(url(w, f"/menu/{iid}"), headers=w.admin, json={"price": "15.00", "is_available": False})
    assert upd.status_code == 200 and Decimal(upd.json()["price"]) == Decimal("15.00") and upd.json()["is_available"] is False
    public = w.client.get(f"/api/v1/menu?restaurant_id={w.a.id}").json()
    assert all(i["id"] != iid for i in public["items"])                       # unavailable items are hidden from customers
    assert w.client.delete(url(w, f"/menu/{iid}"), headers=w.admin).status_code == 204


def test_deleting_a_menu_item_that_was_ordered_is_refused_cleanly(world):
    w = world
    assert place_order(w).status_code == 201
    r = w.client.delete(url(w, f"/menu/{w.item.id}"), headers=w.admin)
    assert r.status_code == 409 and "unavailable" in r.json()["detail"].lower()
    assert w.db.get(MenuItem, w.item.id) is not None


# ---------------------------------------------------------------- modifiers

def test_modifier_lifecycle_and_attaching_to_items(world):
    w = world
    made = w.client.post(url(w, "/modifiers"), headers=w.admin, json={
        "restaurant_id": w.a.id, "name": "Size", "is_required": True, "min_selections": 1, "max_selections": 1,
        "options": [{"name": "Small"}, {"name": "Large", "price_adjustment": "2.50"}]})
    assert made.status_code == 201, made.text
    mod = made.json()
    assert [o["name"] for o in mod["options"]] == ["Small", "Large"]

    added = w.client.post(url(w, f"/modifiers/{mod['id']}/options"), headers=w.admin, json={"name": "Huge", "price_adjustment": "4.00"})
    assert len(added.json()["options"]) == 3
    opt_id = added.json()["options"][-1]["id"]
    edited = w.client.put(url(w, f"/modifier-options/{opt_id}"), headers=w.admin, json={"price_adjustment": "5.00"})
    assert any(Decimal(o["price_adjustment"]) == Decimal("5.00") for o in edited.json()["options"])
    assert len(w.client.delete(url(w, f"/modifier-options/{opt_id}"), headers=w.admin).content) == 0

    attach = w.client.put(url(w, f"/menu/{w.item.id}"), headers=w.admin, json={"modifier_ids": [mod["id"]]})
    assert attach.status_code == 200 and [m["name"] for m in attach.json()["modifiers"]] == ["Size"]
    # A required modifier is enforced when ordering.
    assert place_order(w).status_code == 400
    ok = place_order(w, items=[{"menu_item_id": w.item.id, "quantity": 1, "modifier_option_ids": [mod["options"][1]["id"]]}])
    assert ok.status_code == 201 and Decimal(ok.json()["items"][0]["unit_price"]) == Decimal("14.50")

    assert w.client.put(url(w, f"/menu/{w.item.id}"), headers=w.admin, json={"modifier_ids": [987654]}).status_code == 404
    assert w.client.put(url(w, f"/modifiers/{mod['id']}"), headers=w.admin, json={"name": "Portion"}).json()["name"] == "Portion"


def test_modifiers_are_isolated_between_restaurants(world):
    w = world
    mod_b = w.client.post(url(w, "/modifiers", restaurant=w.b), headers=w.admin_b, json={"restaurant_id": w.b.id, "name": "B-only"}).json()
    r = w.client.put(url(w, f"/menu/{w.item.id}"), headers=w.admin, json={"modifier_ids": [mod_b["id"]]})
    assert r.status_code == 404
    assert w.client.delete(url(w, f"/modifiers/{mod_b['id']}"), headers=w.admin).status_code == 404


# ---------------------------------------------------------------- orders & kitchen

def test_order_list_filters_search_and_pagination(world):
    w = world
    for _ in range(3):
        assert place_order(w).status_code == 201
    everything = w.client.get(url(w, "/orders"), headers=w.staff).json()
    assert everything["total"] == 3 and len(everything["items"]) == 3
    page = w.client.get(url(w, "/orders", page=2, page_size=2), headers=w.staff).json()
    assert page["total"] == 3 and len(page["items"]) == 1 and page["pages"] == 2
    assert w.client.get(url(w, "/orders", status="PREPARING"), headers=w.staff).json()["total"] == 0
    assert w.client.get(url(w, "/orders", status="CONFIRMED"), headers=w.staff).json()["total"] == 3
    assert w.client.get(url(w, "/orders", search="cara"), headers=w.staff).json()["total"] == 3
    assert w.client.get(url(w, "/orders", search="nobody-here"), headers=w.staff).json()["total"] == 0
    assert w.client.get(url(w, "/orders", page_size=1000), headers=w.staff).status_code == 422
    # Another restaurant sees none of it.
    assert w.client.get(url(w, "/orders", restaurant=w.b), headers=w.admin_b).json()["total"] == 0


def test_order_status_flow_and_history(world):
    w = world
    oid = place_order(w).json()["id"]

    def move(status):
        return w.client.patch(url(w, f"/orders/{oid}/status"), headers=w.staff, json={"status": status})

    assert move("READY").status_code == 400                      # can't skip PREPARING
    assert move("PREPARING").status_code == 200
    assert move("READY").json()["status"] == "READY"
    done = move("COMPLETED")
    assert done.status_code == 200
    assert [h["new_status"] for h in done.json()["status_history"]][-3:] == ["PREPARING", "READY", "COMPLETED"]
    assert move("PREPARING").status_code == 400                  # finished orders are frozen


def test_cancelled_orders_cannot_be_reopened_and_other_restaurants_cannot_touch_orders(world):
    w = world
    oid = place_order(w).json()["id"]
    assert w.client.patch(url(w, f"/orders/{oid}/status", restaurant=w.b), headers=w.admin_b, json={"status": "PREPARING"}).status_code == 404
    assert w.client.get(url(w, f"/orders/{oid}", restaurant=w.b), headers=w.admin_b).status_code == 404
    assert w.client.patch(url(w, f"/orders/{oid}/status"), headers=w.staff, json={"status": "CANCELLED", "notes": "Out of stock"}).status_code == 200
    assert w.client.patch(url(w, f"/orders/{oid}/status"), headers=w.staff, json={"status": "PREPARING"}).status_code == 400


def test_kitchen_board_groups_active_orders(world):
    w = world
    ids = [place_order(w).json()["id"] for _ in range(3)]
    w.client.patch(url(w, f"/orders/{ids[1]}/status"), headers=w.staff, json={"status": "PREPARING"})
    w.client.patch(url(w, f"/orders/{ids[2]}/status"), headers=w.staff, json={"status": "PREPARING"})
    w.client.patch(url(w, f"/orders/{ids[2]}/status"), headers=w.staff, json={"status": "READY"})
    board = w.client.get(url(w, "/kitchen"), headers=w.staff).json()
    assert [o["id"] for o in board["new_orders"]] == [ids[0]]
    assert [o["id"] for o in board["preparing"]] == [ids[1]]
    assert [o["id"] for o in board["ready"]] == [ids[2]]
    w.client.patch(url(w, f"/orders/{ids[2]}/status"), headers=w.staff, json={"status": "COMPLETED"})
    assert w.client.get(url(w, "/kitchen"), headers=w.staff).json()["ready"] == []


# ---------------------------------------------------------------- dashboard, customers, settings

def test_dashboard_counts_todays_orders(world):
    w = world
    assert w.client.get(url(w, "/dashboard"), headers=w.staff).json()["today_orders"] == 0
    place_order(w)
    place_order(w)
    stats = w.client.get(url(w, "/dashboard"), headers=w.staff).json()
    assert stats["today_orders"] == 2 and stats["pending_orders"] == 2
    assert Decimal(stats["today_revenue"]) > 0 and Decimal(stats["average_order_value"]) > 0


def test_customer_list_and_detail(world):
    w = world
    assert w.client.get(url(w, "/customers"), headers=w.staff).json() == []
    place_order(w)
    place_order(w)
    rows = w.client.get(url(w, "/customers"), headers=w.staff).json()
    assert len(rows) == 1 and rows[0]["email"] == "am-cust@demo.com" and rows[0]["total_orders"] == 2
    detail = w.client.get(url(w, f"/customers/{w.customer_user.id}"), headers=w.staff).json()
    assert detail["total_orders"] == 2 and len(detail["orders"]) == 2
    assert w.client.get(url(w, "/customers/999999"), headers=w.staff).status_code == 404
    assert w.client.get(url(w, f"/customers/{w.customer_user.id}", restaurant=w.b), headers=w.admin_b).status_code == 404


def test_settings_update_and_validation(world):
    w = world
    ok = w.client.patch(url(w, "/settings"), headers=w.admin, json={
        "description": "Cosy", "tax_rate": "0.0725", "delivery_fee": "3.50", "delivery_enabled": False,
        "opening_hours": {"monday": "09:00-17:00"}})
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["description"] == "Cosy" and Decimal(body["tax_rate"]) == Decimal("0.0725") and body["delivery_enabled"] is False
    assert body["opening_hours"] == {"monday": "09:00-17:00"}
    # Clear it again so the rest of this test isn't at the mercy of what day/time it happens to run.
    assert w.client.patch(url(w, "/settings"), headers=w.admin, json={"opening_hours": None}).json()["opening_hours"] is None
    assert w.client.patch(url(w, "/settings"), headers=w.admin, json={"tax_rate": "1.5"}).status_code == 422
    assert w.client.patch(url(w, "/settings"), headers=w.admin, json={"delivery_fee": "-1"}).status_code == 422
    # A restaurant that has turned delivery off refuses delivery orders.
    r = place_order(w, order_type="DELIVERY", delivery_address={"street": "1 Main", "city": "X", "postal_code": "1"})
    assert r.status_code == 400 and "Delivery" in r.json()["detail"]
    assert w.client.get(url(w, "/settings", restaurant=w.b), headers=w.admin).status_code == 403


def test_kitchen_sees_special_instructions_options_notes_and_table(world):
    """Regression: the kitchen only got 'quantity x name' — instructions and options were dropped."""
    w = world
    mod = w.client.post(url(w, "/modifiers"), headers=w.admin, json={
        "restaurant_id": w.a.id, "name": "Size", "options": [{"name": "Small"}, {"name": "Large", "price_adjustment": "2.00"}]}).json()
    w.client.put(url(w, f"/menu/{w.item.id}"), headers=w.admin, json={"modifier_ids": [mod["id"]]})

    pickup = place_order(w, notes="Birthday — bring candle", items=[{
        "menu_item_id": w.item.id, "quantity": 2, "modifier_option_ids": [mod["options"][1]["id"]],
        "special_instructions": "No onions, extra crispy"}])
    assert pickup.status_code == 201, pickup.text

    table = RestaurantTable(restaurant_id=w.a.id, table_number="K7", capacity=4, status=TableStatus.AVAILABLE)
    w.db.add(table)
    w.db.flush()
    now = datetime.now(timezone.utc)
    reservation = Reservation(
        restaurant_id=w.a.id, table_id=table.id, user_id=w.customer_user.id, party_size=2, guest_name="Cara",
        starts_at=now - timedelta(minutes=1), ends_at=now + timedelta(minutes=89), status=ReservationStatus.CONFIRMED)
    w.db.add(reservation)
    w.db.flush()
    dine_in = place_order(w, order_type="DINE_IN", reservation_id=reservation.id, items=[{
        "menu_item_id": w.item.id, "quantity": 1, "modifier_option_ids": [mod["options"][0]["id"]]}])
    assert dine_in.status_code == 201, dine_in.text

    board = w.client.get(url(w, "/kitchen"), headers=w.staff).json()
    by_id = {o["id"]: o for o in board["new_orders"]}

    a = by_id[pickup.json()["id"]]
    assert a["notes"] == "Birthday — bring candle" and a["order_type"] == "PICKUP" and a["table_number"] is None
    line = a["items"][0]
    assert line["special_instructions"] == "No onions, extra crispy"
    assert [(m["modifier_name"], m["option_name"]) for m in line["modifiers"]] == [("Size", "Large")]

    b = by_id[dine_in.json()["id"]]
    assert b["order_type"] == "DINE_IN" and b["table_number"] == "K7"
    assert b["items"][0]["special_instructions"] is None

    # The same details reach the order detail and the customer's own view.
    detail = w.client.get(url(w, f"/orders/{dine_in.json()['id']}"), headers=w.staff).json()
    assert detail["table_number"] == "K7"
    mine = w.client.get(f"/api/v1/orders/{pickup.json()['id']}", headers=w.customer).json()
    assert mine["items"][0]["special_instructions"] == "No onions, extra crispy"
