"""Guest profiles: every customer shows up (not just those who have ordered), notes/allergies/VIP, and isolation."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.enums import ReservationStatus, TableStatus
from app.models.reservation import Reservation
from app.models.restaurant_table import RestaurantTable
from tests.test_admin_management import place_order, url, world  # noqa: F401  (world is a fixture)

PROFILE = {"notes": "Allergic to shellfish, prefers window seats", "allergies": "Shellfish", "is_vip": True}


def book(w, **extra):
    table = RestaurantTable(restaurant_id=w.a.id, table_number="G1", capacity=4, status=TableStatus.AVAILABLE)
    w.db.add(table)
    w.db.flush()
    start = datetime.now(timezone.utc) + timedelta(days=2)
    reservation = Reservation(
        restaurant_id=w.a.id, table_id=table.id, user_id=w.customer_user.id, party_size=2, guest_name="Cara",
        starts_at=start, ends_at=start + timedelta(minutes=90), status=ReservationStatus.CONFIRMED, **extra,
    )
    w.db.add(reservation)
    w.db.flush()
    return reservation


def patch_profile(w, user_id, who=None, restaurant=None, **data):
    return w.client.patch(url(w, f"/customers/{user_id}", restaurant), headers=who or w.staff, json=data)


# ------------------------------------------------------------------ who shows up

def test_a_customer_who_has_never_ordered_still_shows_up(world):
    w = world
    rows = w.client.get(url(w, "/customers"), headers=w.staff).json()
    assert len(rows) == 1
    row = rows[0]
    assert row["email"] == "am-cust@demo.com" and row["total_orders"] == 0 and row["total_bookings"] == 0
    assert row["last_seen_at"] is None and row["is_vip"] is False


def test_a_booking_only_guest_appears_with_a_booking_count_and_no_order(world):
    w = world
    book(w)
    row = w.client.get(url(w, "/customers"), headers=w.staff).json()[0]
    assert row["total_bookings"] == 1 and row["total_orders"] == 0 and row["last_seen_at"] is not None


def test_last_seen_is_the_more_recent_of_ordering_and_booking(world):
    w = world
    older = book(w)
    older.starts_at = datetime.now(timezone.utc) - timedelta(days=10)
    older.ends_at = older.starts_at + timedelta(minutes=90)
    w.db.flush()
    order = place_order(w)
    assert order.status_code == 201

    row = w.client.get(url(w, "/customers"), headers=w.staff).json()[0]
    order_time = w.db.execute(text("SELECT created_at FROM orders WHERE id = :id"), {"id": order.json()["id"]}).scalar()
    assert abs((datetime.fromisoformat(row["last_seen_at"]) - order_time.replace(tzinfo=timezone.utc)).total_seconds()) < 2


def test_a_staff_or_admin_account_never_appears_as_a_customer(world):
    w = world
    rows = w.client.get(url(w, "/customers"), headers=w.staff).json()
    assert "am-admin@demo.com" not in [r["email"] for r in rows] and "am-staff@demo.com" not in [r["email"] for r in rows]


# ------------------------------------------------------------------ notes, allergies, VIP

def test_staff_can_set_and_clear_a_guest_profile(world):
    w = world
    updated = patch_profile(w, w.customer_user.id, **PROFILE)
    assert updated.status_code == 200
    body = updated.json()
    assert body["notes"] == PROFILE["notes"] and body["allergies"] == "Shellfish" and body["is_vip"] is True

    listed = w.client.get(url(w, "/customers"), headers=w.staff).json()[0]
    assert listed["is_vip"] is True and listed["allergies"] == "Shellfish"

    detail = w.client.get(url(w, f"/customers/{w.customer_user.id}"), headers=w.staff).json()
    assert detail["notes"] == PROFILE["notes"] and detail["is_vip"] is True

    cleared = patch_profile(w, w.customer_user.id, notes=None, allergies=None, is_vip=False)
    assert cleared.json()["notes"] is None and cleared.json()["is_vip"] is False


def test_editing_one_field_leaves_the_others_alone(world):
    w = world
    patch_profile(w, w.customer_user.id, **PROFILE)
    only_vip = patch_profile(w, w.customer_user.id, is_vip=False)
    assert only_vip.json()["is_vip"] is False and only_vip.json()["notes"] == PROFILE["notes"]


def test_a_reservation_shows_the_guests_allergy_note_to_staff(world):
    w = world
    patch_profile(w, w.customer_user.id, **PROFILE)
    reservation = book(w)
    detail = w.client.get(url(w, f"/customers/{w.customer_user.id}"), headers=w.staff).json()
    assert detail["reservations"][0]["id"] == reservation.id and detail["reservations"][0]["table_number"] == "G1"
    assert detail["allergies"] == "Shellfish"


def test_notes_are_length_limited(world):
    w = world
    too_long = patch_profile(w, w.customer_user.id, notes="x" * 4001)
    assert too_long.status_code == 422


# ------------------------------------------------------------------ isolation

def test_a_guest_profile_stays_inside_its_restaurant_and_role(world):
    w = world
    assert patch_profile(w, w.customer_user.id, restaurant=w.b, who=w.admin_b, is_vip=True).status_code == 404
    assert patch_profile(w, w.customer_user.id, who=w.customer, is_vip=True).status_code == 403
    unchanged = w.client.get(url(w, f"/customers/{w.customer_user.id}"), headers=w.staff).json()
    assert unchanged["is_vip"] is False


def test_a_customer_cannot_see_or_edit_their_own_notes_through_this_endpoint(world):
    w = world
    assert w.client.get(url(w, f"/customers/{w.customer_user.id}"), headers=w.customer).status_code == 403