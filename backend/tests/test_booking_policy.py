"""Guest booking policy: party size limits and lead time, enforced on real requests."""

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
        name="Policy Kitchen", slug="policy-kitchen", tax_rate=Decimal("0.1"), delivery_fee=Decimal("2"),
        dine_in_enabled=True, timezone="UTC",
    )
    db.add(restaurant)
    db.flush()
    admin = make_user(db, "policy-admin@iso-demo.com", RoleName.RESTAURANT_ADMIN)
    customer = make_user(db, "policy-cust@iso-demo.com", RoleName.CUSTOMER, restaurant_id=restaurant.id)
    customer2 = make_user(db, "policy-cust2@iso-demo.com", RoleName.CUSTOMER, restaurant_id=restaurant.id)
    db.add(RestaurantUser(restaurant_id=restaurant.id, user_id=admin.id, role=RoleName.RESTAURANT_ADMIN))
    cat = Category(restaurant_id=restaurant.id, name="Mains", slug="mains")
    db.add(cat)
    db.flush()
    db.add(MenuItem(restaurant_id=restaurant.id, category_id=cat.id, name="Soup", price=Decimal("9.00"), is_available=True))
    table = RestaurantTable(restaurant_id=restaurant.id, table_number="P1", capacity=20, status=TableStatus.AVAILABLE)
    table2 = RestaurantTable(restaurant_id=restaurant.id, table_number="P2", capacity=20, status=TableStatus.AVAILABLE)
    db.add_all([table, table2])
    db.flush()
    db.expire_all()
    yield type("W", (), {"client": client, "db": db, "rid": restaurant.id, "restaurant": restaurant, "admin": admin,
                         "customer": customer, "customer2": customer2, "table": table, "table2": table2})
    app.dependency_overrides.clear()


def set_policy(w, **fields):
    r = w.client.patch(f"{API}/admin/settings?restaurant_id={w.rid}", headers=header(w.admin), json=fields)
    assert r.status_code == 200, r.text
    return r.json()


def book(w, starts, party_size=2, headers=None, table=None):
    return w.client.post(f"{API}/restaurants/{w.restaurant.slug}/reservations", headers=headers or header(w.customer), json={
        "table_id": (table or w.table).id, "party_size": party_size, "starts_at": starts.isoformat(), "guest_name": "Cust",
        "guest_email": w.customer.email})


def availability(w, starts, party_size=2):
    return w.client.get(f"{API}/restaurants/{w.restaurant.slug}/reservations/availability", params={
        "starts_at": starts.isoformat(), "party_size": party_size})


def now_utc():
    return datetime.now(timezone.utc)


# ------------------------------------------------------------------ party size

def test_a_party_smaller_than_the_minimum_is_refused(world):
    w = world
    set_policy(w, min_party_size=4)
    starts = now_utc() + timedelta(days=1)
    r = book(w, starts, party_size=2)
    assert r.status_code == 400 and "at least 4" in r.json()["detail"]
    assert availability(w, starts, party_size=2).status_code == 400


def test_a_party_larger_than_the_maximum_is_refused(world):
    w = world
    set_policy(w, max_party_size=6)
    starts = now_utc() + timedelta(days=1)
    r = book(w, starts, party_size=8)
    assert r.status_code == 400 and "larger than 6" in r.json()["detail"]


def test_a_party_within_limits_is_accepted(world):
    w = world
    set_policy(w, min_party_size=2, max_party_size=6)
    r = book(w, now_utc() + timedelta(days=1), party_size=4)
    assert r.status_code == 201, r.text


def test_a_max_smaller_than_the_min_is_refused_by_settings(world):
    w = world
    set_policy(w, min_party_size=6)
    r = w.client.patch(f"{API}/admin/settings?restaurant_id={w.rid}", headers=header(w.admin), json={"max_party_size": 4})
    assert r.status_code == 400


def test_bad_party_size_limits_are_refused(world):
    w = world
    for field, bad in (("min_party_size", 0), ("min_party_size", 21), ("max_party_size", 0), ("max_party_size", 21)):
        r = w.client.patch(f"{API}/admin/settings?restaurant_id={w.rid}", headers=header(w.admin), json={field: bad})
        assert r.status_code == 422, (field, bad)


def test_staff_can_book_outside_party_size_limits(world):
    w = world
    set_policy(w, min_party_size=4, max_party_size=6)
    r = w.client.post(f"{API}/admin/reservations?restaurant_id={w.rid}", headers=header(w.admin), json={
        "table_id": w.table.id, "party_size": 20, "starts_at": (now_utc() + timedelta(hours=3)).isoformat(),
        "duration_minutes": 90, "guest_name": "Private event"})
    assert r.status_code == 201, r.text


# ------------------------------------------------------------------ lead time

def test_a_booking_without_enough_notice_is_refused(world):
    w = world
    set_policy(w, booking_lead_time_minutes=180)
    starts = now_utc() + timedelta(minutes=30)
    r = book(w, starts)
    assert r.status_code == 400 and "notice" in r.json()["detail"].lower()
    assert availability(w, starts).status_code == 400


def test_a_booking_with_enough_notice_is_accepted(world):
    w = world
    set_policy(w, booking_lead_time_minutes=180)
    r = book(w, now_utc() + timedelta(hours=4))
    assert r.status_code == 201, r.text


def test_staff_can_book_inside_the_lead_time(world):
    w = world
    set_policy(w, booking_lead_time_minutes=180)
    r = w.client.post(f"{API}/admin/reservations?restaurant_id={w.rid}", headers=header(w.admin), json={
        "table_id": w.table.id, "party_size": 2, "starts_at": (now_utc() + timedelta(minutes=30)).isoformat(),
        "duration_minutes": 90, "guest_name": "Private event"})
    assert r.status_code == 201, r.text


def test_bad_lead_time_is_refused(world):
    w = world
    for bad in (-1, 20000):
        r = w.client.patch(f"{API}/admin/settings?restaurant_id={w.rid}", headers=header(w.admin), json={"booking_lead_time_minutes": bad})
        assert r.status_code == 422, bad


# ------------------------------------------------------------------ pacing (covers per 15-min slot)

def test_a_slot_over_the_cap_is_refused(world):
    w = world
    set_policy(w, max_covers_per_slot=6)
    starts = now_utc() + timedelta(days=1)
    first = book(w, starts, party_size=4, headers=header(w.customer))
    assert first.status_code == 201, first.text
    second = book(w, starts, party_size=4, headers=header(w.customer2), table=w.table2)
    assert second.status_code == 400 and "fully booked" in second.json()["detail"].lower()
    assert availability(w, starts, party_size=4).status_code == 400


def test_a_slot_at_or_under_the_cap_is_accepted(world):
    w = world
    set_policy(w, max_covers_per_slot=6)
    starts = now_utc() + timedelta(days=1)
    first = book(w, starts, party_size=4, headers=header(w.customer))
    assert first.status_code == 201, first.text
    second = book(w, starts, party_size=2, headers=header(w.customer2), table=w.table2)
    assert second.status_code == 201, second.text


def test_pacing_only_counts_the_same_15_minute_slot(world):
    w = world
    set_policy(w, max_covers_per_slot=4)
    bucket = (now_utc() + timedelta(days=1)).replace(minute=0, second=0, microsecond=0)
    first = book(w, bucket, party_size=4, headers=header(w.customer))
    assert first.status_code == 201, first.text
    # 15 minutes later is a different slot, so the cap doesn't carry over
    later = book(w, bucket + timedelta(minutes=15), party_size=4, headers=header(w.customer2), table=w.table2)
    assert later.status_code == 201, later.text


def test_cancelled_bookings_free_up_the_slot(world):
    w = world
    set_policy(w, max_covers_per_slot=4)
    starts = now_utc() + timedelta(days=1)
    first = book(w, starts, party_size=4, headers=header(w.customer)).json()
    w.client.post(f"{API}/reservations/{first['id']}/cancel", headers=header(w.customer))
    second = book(w, starts, party_size=4, headers=header(w.customer2), table=w.table2)
    assert second.status_code == 201, second.text


def test_staff_can_book_over_the_pacing_cap(world):
    w = world
    set_policy(w, max_covers_per_slot=2)
    starts = now_utc() + timedelta(hours=3)
    r = w.client.post(f"{API}/admin/reservations?restaurant_id={w.rid}", headers=header(w.admin), json={
        "table_id": w.table.id, "party_size": 10, "starts_at": starts.isoformat(),
        "duration_minutes": 90, "guest_name": "Private event"})
    assert r.status_code == 201, r.text


def test_bad_pacing_cap_is_refused(world):
    w = world
    for bad in (0, 1001):
        r = w.client.patch(f"{API}/admin/settings?restaurant_id={w.rid}", headers=header(w.admin), json={"max_covers_per_slot": bad})
        assert r.status_code == 422, bad
