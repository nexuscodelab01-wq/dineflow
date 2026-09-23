"""Walk-in waitlist: add, notify ("your table is ready"), seat and cancel."""

from decimal import Decimal

import pytest
from sqlalchemy import text

from app.db.session import get_db
from app.main import app
from app.models.category import Category
from app.models.enums import RoleName, TableStatus
from app.models.menu_item import MenuItem
from app.models.restaurant import Restaurant
from app.models.restaurant_table import RestaurantTable
from app.models.restaurant_user import RestaurantUser
from tests.conftest import override_get_db
from tests.tenants import header, make_user

API = "/api/v1"


@pytest.fixture
def world(client, db):
    app.dependency_overrides[get_db] = override_get_db(db)
    restaurant = Restaurant(
        name="Waitlist Kitchen", slug="waitlist-kitchen", tax_rate=Decimal("0.1"), delivery_fee=Decimal("2"),
        dine_in_enabled=True, timezone="UTC",
    )
    db.add(restaurant)
    db.flush()
    admin = make_user(db, "waitlist-admin@iso-demo.com", RoleName.RESTAURANT_ADMIN)
    staff = make_user(db, "waitlist-staff@iso-demo.com", RoleName.RESTAURANT_STAFF)
    customer = make_user(db, "waitlist-cust@iso-demo.com", RoleName.CUSTOMER, restaurant_id=restaurant.id)
    db.add_all([RestaurantUser(restaurant_id=restaurant.id, user_id=admin.id), RestaurantUser(restaurant_id=restaurant.id, user_id=staff.id)])
    cat = Category(restaurant_id=restaurant.id, name="Mains", slug="mains")
    db.add(cat)
    db.flush()
    db.add(MenuItem(restaurant_id=restaurant.id, category_id=cat.id, name="Soup", price=Decimal("9.00"), is_available=True))
    table = RestaurantTable(restaurant_id=restaurant.id, table_number="W1", capacity=4, status=TableStatus.AVAILABLE)
    small_table = RestaurantTable(restaurant_id=restaurant.id, table_number="W2", capacity=2, status=TableStatus.AVAILABLE)
    db.add_all([table, small_table])
    db.flush()
    db.expire_all()
    yield type("W", (), {"client": client, "db": db, "rid": restaurant.id, "restaurant": restaurant, "admin": admin,
                         "staff": staff, "customer": customer, "table": table, "small_table": small_table})
    app.dependency_overrides.clear()


def add(w, **fields):
    data = {"guest_name": "Walk In", "party_size": 2, **fields}
    return w.client.post(f"{API}/admin/waitlist?restaurant_id={w.rid}", headers=header(w.admin), json=data)


def queued(db, subject_contains=None):
    rows = db.execute(text("SELECT id, payload, run_at, dedupe_key, status FROM jobs WHERE type = 'send_email' ORDER BY id")).all()
    return [r for r in rows if subject_contains is None or subject_contains in r.payload["subject"]]


# ------------------------------------------------------------------ adding & listing

def test_a_platform_admin_can_add_and_list_a_walk_in(world):
    w = world
    r = add(w, guest_name="Sam", party_size=3, guest_email="sam@example.com", quoted_minutes=15)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["guest_name"] == "Sam" and body["party_size"] == 3 and body["status"] == "WAITING"
    assert body["waiting_minutes"] == 0

    listed = w.client.get(f"{API}/admin/waitlist?restaurant_id={w.rid}", headers=header(w.staff))
    assert listed.status_code == 200 and len(listed.json()) == 1 and listed.json()[0]["guest_name"] == "Sam"


def test_the_queue_lists_oldest_first(world):
    w = world
    add(w, guest_name="First")
    add(w, guest_name="Second")
    names = [e["guest_name"] for e in w.client.get(f"{API}/admin/waitlist?restaurant_id={w.rid}", headers=header(w.staff)).json()]
    assert names == ["First", "Second"]


def test_bad_input_is_refused(world):
    w = world
    assert add(w, party_size=0).status_code == 422
    assert add(w, party_size=21).status_code == 422
    assert add(w, guest_name="").status_code == 422


# ------------------------------------------------------------------ notify

def test_notifying_a_guest_emails_them_and_moves_them_to_notified(world):
    w = world
    entry_id = add(w, guest_email="sam@example.com").json()["id"]
    r = w.client.post(f"{API}/admin/waitlist/{entry_id}/notify?restaurant_id={w.rid}", headers=header(w.staff))
    assert r.status_code == 200 and r.json()["status"] == "NOTIFIED" and r.json()["notified_at"]
    [email] = queued(w.db, "is ready")
    assert email.status == "queued"


def test_notifying_a_guest_with_no_email_sends_nothing_but_still_updates_status(world):
    w = world
    entry_id = add(w).json()["id"]
    r = w.client.post(f"{API}/admin/waitlist/{entry_id}/notify?restaurant_id={w.rid}", headers=header(w.staff))
    assert r.status_code == 200 and r.json()["status"] == "NOTIFIED"
    assert queued(w.db, "is ready") == []


def test_notifying_twice_is_refused(world):
    w = world
    entry_id = add(w).json()["id"]
    w.client.post(f"{API}/admin/waitlist/{entry_id}/notify?restaurant_id={w.rid}", headers=header(w.staff))
    again = w.client.post(f"{API}/admin/waitlist/{entry_id}/notify?restaurant_id={w.rid}", headers=header(w.staff))
    assert again.status_code == 400


# ------------------------------------------------------------------ seat

def test_seating_a_walk_in_creates_a_seated_reservation_and_occupies_the_table(world):
    w = world
    entry_id = add(w, guest_name="Sam", party_size=2).json()["id"]
    r = w.client.post(f"{API}/admin/waitlist/{entry_id}/seat?restaurant_id={w.rid}", headers=header(w.staff), json={"table_id": w.table.id})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "SEATED" and body["reservation_id"]

    res = w.client.get(f"{API}/admin/reservations?restaurant_id={w.rid}", headers=header(w.staff)).json()
    [seated] = [x for x in res if x["id"] == body["reservation_id"]]
    assert seated["status"] == "SEATED" and seated["guest_name"] == "Sam" and seated["table_id"] == w.table.id

    tables = w.client.get(f"{API}/admin/tables?restaurant_id={w.rid}", headers=header(w.staff)).json()
    [seated_table] = [t for t in tables if t["id"] == w.table.id]
    assert seated_table["status"] == "OCCUPIED"

    # no longer on the active waitlist
    active = w.client.get(f"{API}/admin/waitlist?restaurant_id={w.rid}", headers=header(w.staff)).json()
    assert active == []


def test_seating_onto_a_table_too_small_is_refused(world):
    w = world
    entry_id = add(w, party_size=4).json()["id"]
    r = w.client.post(f"{API}/admin/waitlist/{entry_id}/seat?restaurant_id={w.rid}", headers=header(w.staff), json={"table_id": w.small_table.id})
    assert r.status_code == 400 and "capacity" in r.json()["detail"].lower()


def test_a_seated_or_cancelled_entry_cannot_be_seated_again(world):
    w = world
    entry_id = add(w).json()["id"]
    w.client.post(f"{API}/admin/waitlist/{entry_id}/seat?restaurant_id={w.rid}", headers=header(w.staff), json={"table_id": w.table.id})
    again = w.client.post(f"{API}/admin/waitlist/{entry_id}/seat?restaurant_id={w.rid}", headers=header(w.staff), json={"table_id": w.small_table.id})
    assert again.status_code == 400


# ------------------------------------------------------------------ cancel

def test_cancelling_removes_a_guest_from_the_active_queue(world):
    w = world
    entry_id = add(w, guest_name="Sam").json()["id"]
    r = w.client.post(f"{API}/admin/waitlist/{entry_id}/cancel?restaurant_id={w.rid}", headers=header(w.staff))
    assert r.status_code == 200 and r.json()["status"] == "CANCELLED"
    assert w.client.get(f"{API}/admin/waitlist?restaurant_id={w.rid}", headers=header(w.staff)).json() == []


def test_only_staff_can_manage_the_waitlist(world):
    w = world
    entry_id = add(w).json()["id"]
    assert w.client.get(f"{API}/admin/waitlist?restaurant_id={w.rid}", headers=header(w.customer)).status_code == 403
    assert w.client.post(f"{API}/admin/waitlist/{entry_id}/cancel?restaurant_id={w.rid}", headers=header(w.customer)).status_code == 403
