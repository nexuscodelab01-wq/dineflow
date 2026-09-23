"""Table combining: a staff booking for a large party can span more than one table."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

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
        name="Combine Kitchen", slug="combine-kitchen", tax_rate=Decimal("0.1"), delivery_fee=Decimal("2"),
        dine_in_enabled=True, timezone="UTC",
    )
    db.add(restaurant)
    db.flush()
    admin = make_user(db, "combine-admin@iso-demo.com", RoleName.RESTAURANT_ADMIN)
    db.add(RestaurantUser(restaurant_id=restaurant.id, user_id=admin.id))
    cat = Category(restaurant_id=restaurant.id, name="Mains", slug="mains")
    db.add(cat)
    db.flush()
    db.add(MenuItem(restaurant_id=restaurant.id, category_id=cat.id, name="Soup", price=Decimal("9.00"), is_available=True))
    a = RestaurantTable(restaurant_id=restaurant.id, table_number="A", capacity=4, status=TableStatus.AVAILABLE)
    b = RestaurantTable(restaurant_id=restaurant.id, table_number="B", capacity=4, status=TableStatus.AVAILABLE)
    c = RestaurantTable(restaurant_id=restaurant.id, table_number="C", capacity=4, status=TableStatus.AVAILABLE)
    db.add_all([a, b, c])
    db.flush()
    db.expire_all()
    yield type("W", (), {"client": client, "db": db, "rid": restaurant.id, "restaurant": restaurant, "admin": admin,
                         "a": a, "b": b, "c": c})
    app.dependency_overrides.clear()


def now_utc():
    return datetime.now(timezone.utc)


def create(w, table, extra_table_ids=None, party_size=6, starts=None, **extra):
    starts = starts or now_utc() + timedelta(days=1)
    return w.client.post(f"{API}/admin/reservations?restaurant_id={w.rid}", headers=header(w.admin), json={
        "table_id": table.id, "extra_table_ids": extra_table_ids or [], "party_size": party_size,
        "starts_at": starts.isoformat(), "duration_minutes": 90, "guest_name": "Big Party", **extra})


def tables(w):
    return {t["table_number"]: t for t in w.client.get(f"{API}/admin/tables?restaurant_id={w.rid}", headers=header(w.admin)).json()}


# ------------------------------------------------------------------ creating

def test_a_party_too_big_for_one_table_is_refused_without_combining(world):
    w = world
    r = create(w, w.a, party_size=6)  # table A alone only seats 4
    assert r.status_code == 400 and "capacity" in r.json()["detail"].lower()


def test_combining_tables_fits_a_large_party(world):
    w = world
    r = create(w, w.a, extra_table_ids=[w.b.id], party_size=6)  # 4 + 4 = 8 >= 6
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["table_id"] == w.a.id and body["extra_table_ids"] == [w.b.id] and body["extra_table_numbers"] == ["B"]


def test_a_table_cannot_be_combined_with_itself(world):
    w = world
    r = create(w, w.a, extra_table_ids=[w.a.id], party_size=6)
    assert r.status_code == 400 and "itself" in r.json()["detail"].lower()


def test_combining_with_someone_elses_table_is_refused(world):
    w = world
    starts = now_utc() + timedelta(days=1)
    taken = create(w, w.b, party_size=2, starts=starts)
    assert taken.status_code == 201
    r = create(w, w.a, extra_table_ids=[w.b.id], party_size=6, starts=starts)
    assert r.status_code == 400 and "already booked" in r.json()["detail"].lower()


def test_combined_tables_both_show_as_reserved_on_the_floor(world):
    w = world
    r = create(w, w.a, extra_table_ids=[w.b.id], party_size=6, starts=now_utc() + timedelta(minutes=30))
    assert r.status_code == 201, r.text
    t = tables(w)
    assert t["A"]["status"] == "RESERVED" and t["B"]["status"] == "RESERVED"


def test_seating_a_combined_booking_occupies_both_tables(world):
    w = world
    r = w.client.post(f"{API}/admin/reservations?restaurant_id={w.rid}", headers=header(w.admin), json={
        "table_id": w.a.id, "extra_table_ids": [w.b.id], "party_size": 6, "starts_at": now_utc().isoformat(),
        "duration_minutes": 90, "guest_name": "Walk-in party", "seat_immediately": True})
    assert r.status_code == 201, r.text
    t = tables(w)
    assert t["A"]["status"] == "OCCUPIED" and t["B"]["status"] == "OCCUPIED"


def test_completing_a_combined_booking_frees_both_tables(world):
    w = world
    created = w.client.post(f"{API}/admin/reservations?restaurant_id={w.rid}", headers=header(w.admin), json={
        "table_id": w.a.id, "extra_table_ids": [w.b.id], "party_size": 6, "starts_at": now_utc().isoformat(),
        "duration_minutes": 90, "guest_name": "Walk-in party", "seat_immediately": True}).json()
    r = w.client.patch(f"{API}/admin/reservations/{created['id']}/status?restaurant_id={w.rid}", headers=header(w.admin), json={"status": "COMPLETED"})
    assert r.status_code == 200, r.text
    t = tables(w)
    assert t["A"]["status"] == "AVAILABLE" and t["B"]["status"] == "AVAILABLE"


def test_cancelling_a_combined_booking_frees_both_tables(world):
    w = world
    created = create(w, w.a, extra_table_ids=[w.b.id], party_size=6, starts=now_utc() + timedelta(minutes=30)).json()
    r = w.client.patch(f"{API}/admin/reservations/{created['id']}/status?restaurant_id={w.rid}", headers=header(w.admin), json={"status": "CANCELLED"})
    assert r.status_code == 200, r.text
    t = tables(w)
    assert t["A"]["status"] == "AVAILABLE" and t["B"]["status"] == "AVAILABLE"


# ------------------------------------------------------------------ editing

def test_adding_a_third_table_to_an_existing_booking(world):
    w = world
    created = create(w, w.a, extra_table_ids=[w.b.id], party_size=6, starts=now_utc() + timedelta(minutes=30)).json()
    r = w.client.patch(f"{API}/admin/reservations/{created['id']}?restaurant_id={w.rid}", headers=header(w.admin), json={
        "extra_table_ids": [w.b.id, w.c.id], "party_size": 10})
    assert r.status_code == 200, r.text
    assert set(r.json()["extra_table_ids"]) == {w.b.id, w.c.id}
    t = tables(w)
    assert t["C"]["status"] == "RESERVED"


def test_dropping_back_to_a_single_table_frees_the_extra(world):
    w = world
    created = create(w, w.a, extra_table_ids=[w.b.id], party_size=4, starts=now_utc() + timedelta(minutes=30)).json()
    r = w.client.patch(f"{API}/admin/reservations/{created['id']}?restaurant_id={w.rid}", headers=header(w.admin), json={"extra_table_ids": []})
    assert r.status_code == 200 and r.json()["extra_table_ids"] == []
    t = tables(w)
    assert t["B"]["status"] == "AVAILABLE"


def test_a_seated_combined_booking_cannot_have_its_tables_changed(world):
    w = world
    created = w.client.post(f"{API}/admin/reservations?restaurant_id={w.rid}", headers=header(w.admin), json={
        "table_id": w.a.id, "extra_table_ids": [w.b.id], "party_size": 6, "starts_at": now_utc().isoformat(),
        "duration_minutes": 90, "guest_name": "Walk-in party", "seat_immediately": True}).json()
    r = w.client.patch(f"{API}/admin/reservations/{created['id']}?restaurant_id={w.rid}", headers=header(w.admin), json={"extra_table_ids": [w.c.id]})
    assert r.status_code == 400 and "seated" in r.json()["detail"].lower()


# ------------------------------------------------------------------ extending

def test_extending_checks_every_combined_table_for_clashes(world):
    w = world
    starts = now_utc()
    seated = w.client.post(f"{API}/admin/reservations?restaurant_id={w.rid}", headers=header(w.admin), json={
        "table_id": w.a.id, "extra_table_ids": [w.b.id], "party_size": 6, "starts_at": starts.isoformat(),
        "duration_minutes": 60, "guest_name": "Walk-in party", "seat_immediately": True}).json()
    # Someone else books table B — far enough out to not clash with the current 60-min booking (plus its
    # 15-min buffer), but close enough that extending by 30 minutes would clash.
    next_up = w.client.post(f"{API}/admin/reservations?restaurant_id={w.rid}", headers=header(w.admin), json={
        "table_id": w.b.id, "party_size": 2, "starts_at": (starts + timedelta(minutes=85)).isoformat(),
        "duration_minutes": 90, "guest_name": "Next up"})
    assert next_up.status_code == 201, next_up.text
    r = w.client.post(f"{API}/admin/reservations/{seated['id']}/extend?restaurant_id={w.rid}", headers=header(w.admin), json={"minutes": 30})
    assert r.status_code == 400 and "booked next" in r.json()["detail"].lower()
