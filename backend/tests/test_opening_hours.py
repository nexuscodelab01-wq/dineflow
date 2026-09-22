"""Opening hours enforced on real requests: ordering, booking, staff overrides, settings, and reminder emails."""

from datetime import datetime, timedelta, timezone
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

WEEKLY = {"monday": "00:00-23:59", "tuesday": "00:00-23:59", "wednesday": "00:00-23:59", "thursday": "00:00-23:59",
          "friday": "00:00-23:59", "saturday": "00:00-23:59", "sunday": "closed"}


@pytest.fixture
def world(client, db):
    app.dependency_overrides[get_db] = override_get_db(db)
    restaurant = Restaurant(
        name="Hours Kitchen", slug="hours-kitchen", tax_rate=Decimal("0.1"), delivery_fee=Decimal("2"),
        dine_in_enabled=True, timezone="UTC",
    )
    db.add(restaurant)
    db.flush()
    admin = make_user(db, "hours-admin@iso-demo.com", RoleName.RESTAURANT_ADMIN)
    customer = make_user(db, "hours-cust@iso-demo.com", RoleName.CUSTOMER, restaurant_id=restaurant.id)
    db.add(RestaurantUser(restaurant_id=restaurant.id, user_id=admin.id))
    cat = Category(restaurant_id=restaurant.id, name="Mains", slug="mains")
    db.add(cat)
    db.flush()
    item = MenuItem(restaurant_id=restaurant.id, category_id=cat.id, name="Soup", price=Decimal("9.00"), is_available=True)
    table = RestaurantTable(restaurant_id=restaurant.id, table_number="H1", capacity=4, status=TableStatus.AVAILABLE)
    db.add_all([item, table])
    db.flush()
    db.expire_all()
    yield type("W", (), {"client": client, "db": db, "rid": restaurant.id, "restaurant": restaurant, "admin": admin,
                         "customer": customer, "item": item, "table": table})
    app.dependency_overrides.clear()


def set_hours(w, hours=None, tz=None, closures=None):
    fields = {}
    if hours is not None:
        fields["opening_hours"] = hours
    if tz is not None:
        fields["timezone"] = tz
    if closures is not None:
        fields["closures"] = closures
    r = w.client.patch(f"{API}/admin/settings?restaurant_id={w.rid}", headers=header(w.admin), json=fields)
    assert r.status_code == 200, r.text
    return r.json()


def order(w, **extra):
    return w.client.post(f"{API}/orders", headers=header(w.customer), json={
        "restaurant_id": w.rid, "order_type": "PICKUP", "customer_name": "Cust", "customer_email": w.customer.email,
        "items": [{"menu_item_id": w.item.id, "quantity": 1, "modifier_option_ids": []}], **extra})


def book(w, starts, headers=None, **extra):
    return w.client.post(f"{API}/restaurants/{w.restaurant.slug}/reservations", headers=headers or header(w.customer), json={
        "table_id": w.table.id, "party_size": 2, "starts_at": starts.isoformat(), "guest_name": "Cust",
        "guest_email": w.customer.email, **extra})


def availability(w, starts):
    return w.client.get(f"{API}/restaurants/{w.restaurant.slug}/reservations/availability", params={
        "starts_at": starts.isoformat(), "party_size": 2})


def now_utc():
    return datetime.now(timezone.utc)


def next_weekday(target: int, min_days_ahead: int = 2) -> datetime:
    """The next date (at least `min_days_ahead` away) that falls on weekday `target` (Monday=0 .. Sunday=6)."""
    d = now_utc().replace(hour=13, minute=0, second=0, microsecond=0) + timedelta(days=min_days_ahead)
    while d.weekday() != target:
        d += timedelta(days=1)
    return d


def queued(db, subject_contains=None):
    rows = db.execute(text("SELECT id, payload, run_at, dedupe_key, status FROM jobs WHERE type = 'send_email' ORDER BY id")).all()
    return [r for r in rows if subject_contains is None or subject_contains in r.payload["subject"]]


# ------------------------------------------------------------------ settings validation

def test_admins_can_set_hours_timezone_and_closures(world):
    w = world
    saved = set_hours(w, hours=WEEKLY, tz="America/Los_Angeles", closures=[{"date": "2026-12-25", "label": "Christmas"}])
    assert saved["opening_hours"]["monday"] == "00:00-23:59" and saved["timezone"] == "America/Los_Angeles"
    assert saved["closures"] == [{"date": "2026-12-25", "label": "Christmas"}]


def test_bad_hours_timezone_or_closures_are_refused(world):
    w = world
    patch = lambda field, value: w.client.patch(f"{API}/admin/settings?restaurant_id={w.rid}", headers=header(w.admin), json={field: value})  # noqa: E731
    assert patch("opening_hours", {"someday": "9-5"}).status_code == 422
    assert patch("opening_hours", {"monday": "not a range"}).status_code == 422
    assert patch("timezone", "Mars/Nowhere").status_code == 422
    assert patch("closures", [{"date": "not a date"}]).status_code == 422
    assert patch("closures", [{"no": "date"}]).status_code == 422


def test_a_restaurant_with_no_hours_set_is_always_open(world):
    w = world
    assert order(w).status_code == 201
    assert book(w, now_utc() + timedelta(hours=5)).status_code == 201


# ------------------------------------------------------------------ ordering

def test_ordering_is_refused_while_closed_and_works_once_open(world):
    w = world
    set_hours(w, hours={**WEEKLY, **{d: "closed" for d in WEEKLY}})   # closed every day
    closed = order(w)
    assert closed.status_code == 400 and "closed" in closed.json()["detail"].lower()
    set_hours(w, hours=WEEKLY)                                       # open all day except Sunday
    today = now_utc().strftime("%A").lower()
    if today == "sunday":
        assert order(w).status_code == 400
    else:
        assert order(w).status_code == 201


def test_a_todays_closure_blocks_ordering_even_though_the_weekly_hours_are_open(world):
    w = world
    today = now_utc().date().isoformat()
    set_hours(w, hours=WEEKLY, closures=[{"date": today, "label": "Deep clean"}])
    r = order(w)
    assert r.status_code == 400 and "Deep clean" in r.json()["detail"]


# ------------------------------------------------------------------ booking

def test_a_booking_outside_hours_is_refused_and_one_inside_hours_works(world):
    w = world
    set_hours(w, hours={"monday": "11:00-22:00", "tuesday": "11:00-22:00", "wednesday": "11:00-22:00",
                        "thursday": "11:00-22:00", "friday": "11:00-22:00", "saturday": "11:00-22:00", "sunday": "closed"})
    outside = book(w, next_weekday(6))    # Sunday: closed
    assert outside.status_code == 400 and "closed" in outside.json()["detail"].lower()

    inside = book(w, next_weekday(0))     # Monday 13:00: within 11:00-22:00
    assert inside.status_code == 201, inside.text


def test_availability_also_respects_hours(world):
    w = world
    set_hours(w, hours={d: "closed" for d in WEEKLY})
    r = availability(w, now_utc() + timedelta(days=2))
    assert r.status_code == 400 and "closed" in r.json()["detail"].lower()


def test_staff_can_book_outside_posted_hours(world):
    w = world
    set_hours(w, hours={d: "closed" for d in WEEKLY})     # closed every day
    r = w.client.post(f"{API}/admin/reservations?restaurant_id={w.rid}", headers=header(w.admin), json={
        "table_id": w.table.id, "party_size": 2, "starts_at": (now_utc() + timedelta(hours=3)).isoformat(),
        "duration_minutes": 90, "guest_name": "Private event"})
    assert r.status_code == 201, r.text


# ------------------------------------------------------------------ reminder emails

def test_confirming_a_booking_with_plenty_of_notice_schedules_a_reminder(world):
    w = world
    starts = now_utc() + timedelta(hours=10)
    res = book(w, starts).json()
    [reminder] = queued(w.db, "See you soon")
    assert reminder.dedupe_key == f"email:reservation:{res['id']}:reminder"
    assert reminder.run_at < starts - timedelta(hours=2, minutes=45) and reminder.run_at > starts - timedelta(hours=3, minutes=15)
    assert reminder.status == "queued"


def test_a_booking_too_soon_for_a_reminder_to_help_gets_none(world):
    w = world
    book(w, now_utc() + timedelta(hours=1))
    assert queued(w.db, "See you soon") == []


def test_cancelling_a_booking_cancels_its_reminder(world):
    w = world
    res = book(w, now_utc() + timedelta(hours=10)).json()
    assert len(queued(w.db, "See you soon")) == 1
    w.client.post(f"{API}/reservations/{res['id']}/cancel", headers=header(w.customer))
    [reminder] = queued(w.db, "See you soon")
    assert reminder.status == "cancelled"


def test_rescheduling_a_booking_moves_its_reminder(world):
    w = world
    res = book(w, now_utc() + timedelta(hours=10)).json()
    first_run_at = queued(w.db, "See you soon")[0].run_at
    new_start = now_utc() + timedelta(hours=30)
    w.client.patch(f"{API}/admin/reservations/{res['id']}?restaurant_id={w.rid}", headers=header(w.admin),
                  json={"starts_at": new_start.isoformat()})
    active = [j for j in queued(w.db, "See you soon") if j.status == "queued"]
    assert len(active) == 1 and active[0].run_at != first_run_at
    assert active[0].run_at > first_run_at


def test_a_walk_in_seated_immediately_gets_no_reminder(world):
    w = world
    r = w.client.post(f"{API}/admin/reservations?restaurant_id={w.rid}", headers=header(w.admin), json={
        "table_id": w.table.id, "party_size": 2, "starts_at": now_utc().isoformat(), "duration_minutes": 90,
        "guest_name": "Walk In", "seat_immediately": True})
    assert r.status_code == 201
    assert queued(w.db, "See you soon") == []
