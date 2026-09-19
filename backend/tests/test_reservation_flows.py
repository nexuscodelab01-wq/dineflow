"""Reservation lifecycle tests: admin cancel/release/seat, slot-aware availability, editing."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password
from app.db.session import get_db
from app.main import app
from app.models.enums import ReservationStatus, RoleName, TableStatus
from app.models.reservation import Reservation
from app.models.restaurant import Restaurant
from app.models.restaurant_table import RestaurantTable
from app.models.restaurant_user import RestaurantUser
from app.models.role import Role
from app.models.user import User
from tests.conftest import override_get_db


def _header(user: User) -> dict[str, str]:
    role = user.role.name.value if hasattr(user.role.name, "value") else str(user.role.name)
    return {"Authorization": f"Bearer {create_access_token(str(user.id), claims={'role': role})}"}


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


@pytest.fixture
def world(client: TestClient, db: Session):
    """Restaurant with an admin, a customer and three tables (T1/T2 seat 2, T3 seats 6)."""
    app.dependency_overrides[get_db] = override_get_db(db)
    admin_role = db.query(Role).filter(Role.name == RoleName.RESTAURANT_ADMIN.value).one()
    cust_role = db.query(Role).filter(Role.name == RoleName.CUSTOMER.value).one()
    admin = User(email="rf-admin@demo.com", hashed_password=hash_password("x"), first_name="A", last_name="Dmin", role_id=admin_role.id)
    customer = User(email="rf-cust@demo.com", hashed_password=hash_password("x"), first_name="C", last_name="Ust", role_id=cust_role.id)
    restaurant = Restaurant(name="Flow Kitchen", slug="flow-kitchen", tax_rate=Decimal("0.1"), delivery_fee=Decimal("1"), dine_in_enabled=True)
    db.add_all([admin, customer, restaurant])
    db.flush()
    db.add(RestaurantUser(restaurant_id=restaurant.id, user_id=admin.id))
    tables = [RestaurantTable(restaurant_id=restaurant.id, table_number=n, capacity=c, status=TableStatus.AVAILABLE)
              for n, c in (("T1", 2), ("T2", 2), ("T3", 6))]
    db.add_all(tables)
    db.flush()
    db.expire_all()
    admin = db.get(User, admin.id)
    customer = db.get(User, customer.id)
    yield type("W", (), {
        "client": client, "db": db, "admin": admin, "customer": customer,
        "restaurant": restaurant, "t1": tables[0], "t2": tables[1], "t3": tables[2],
        "ah": _header(admin), "ch": _header(customer),
        "rid": restaurant.id,
    })
    app.dependency_overrides.clear()


def _book(w, table, starts, minutes=90, party=2, headers=None, **extra):
    body = {"table_id": table.id, "party_size": party, "starts_at": _iso(starts),
            "duration_minutes": minutes, "guest_name": "Guest", **extra}
    return w.client.post(f"/api/v1/restaurants/{w.restaurant.slug}/reservations", headers=headers or w.ch, json=body)


def _table_status(w, table):
    rows = w.client.get(f"/api/v1/admin/tables?restaurant_id={w.rid}", headers=w.ah).json()
    return next(t for t in rows if t["id"] == table.id)


def _now():
    return datetime.now(timezone.utc).replace(microsecond=0)


def test_admin_cancel_frees_table_floor_status(world):
    w = world
    soon = _now() + timedelta(minutes=30)
    res = _book(w, w.t1, soon)
    assert res.status_code == 201, res.text
    assert _table_status(w, w.t1)["status"] == "RESERVED"

    r = w.client.patch(
        f"/api/v1/admin/reservations/{res.json()['id']}/status?restaurant_id={w.rid}",
        headers=w.ah, json={"status": "CANCELLED"},
    )
    assert r.status_code == 200, r.text
    assert _table_status(w, w.t1)["status"] == "AVAILABLE"


def test_release_table_requires_force_then_cancels_reservation(world):
    w = world
    res = _book(w, w.t1, _now() + timedelta(minutes=30)).json()

    blocked = w.client.patch(
        f"/api/v1/admin/tables/{w.t1.id}/status?restaurant_id={w.rid}",
        headers=w.ah, json={"status": "AVAILABLE"},
    )
    assert blocked.status_code == 409
    assert _table_status(w, w.t1)["status"] == "RESERVED"

    ok = w.client.patch(
        f"/api/v1/admin/tables/{w.t1.id}/status?restaurant_id={w.rid}",
        headers=w.ah, json={"status": "AVAILABLE", "force": True},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["cancelled_reservations"] == 1
    assert _table_status(w, w.t1)["status"] == "AVAILABLE"

    listed = w.client.get(f"/api/v1/admin/reservations?restaurant_id={w.rid}", headers=w.ah).json()
    assert next(r for r in listed if r["id"] == res["id"])["status"] == "CANCELLED"


def test_release_seated_table_completes_reservation(world):
    w = world
    r = w.client.post(
        f"/api/v1/admin/reservations?restaurant_id={w.rid}", headers=w.ah,
        json={"table_id": w.t1.id, "party_size": 2, "starts_at": _iso(_now()), "guest_name": "Walk In", "seat_immediately": True},
    )
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "SEATED"
    assert _table_status(w, w.t1)["status"] == "OCCUPIED"

    ok = w.client.patch(
        f"/api/v1/admin/tables/{w.t1.id}/status?restaurant_id={w.rid}",
        headers=w.ah, json={"status": "AVAILABLE", "force": True},
    )
    assert ok.json()["completed_reservations"] == 1
    listed = w.client.get(f"/api/v1/admin/reservations?restaurant_id={w.rid}", headers=w.ah).json()
    assert listed[0]["status"] == "COMPLETED"
    assert _table_status(w, w.t1)["status"] == "AVAILABLE"


def test_admin_availability_is_time_aware(world):
    w = world
    three = _now() + timedelta(hours=3)
    assert _book(w, w.t1, three, minutes=120).status_code == 201  # holds 3h..5h from now

    def slot(start, minutes=90):
        r = w.client.get(
            "/api/v1/admin/reservations/availability", headers=w.ah,
            params={"restaurant_id": w.rid, "starts_at": _iso(start), "party_size": 2, "duration_minutes": minutes},
        )
        assert r.status_code == 200, r.text
        return {t["table_number"]: t for t in r.json()["tables"]}

    inside = slot(three + timedelta(minutes=30))
    assert inside["T1"]["slot_status"] == "RESERVED" and inside["T1"]["available"] is False
    assert inside["T1"]["conflicts"][0]["guest_name"] == "Guest"
    assert inside["T2"]["available"] is True

    # Default 15-minute turnover buffer: the table needs resetting before the next party.
    assert slot(three + timedelta(hours=2))["T1"]["slot_status"] == "RESERVED"
    after = slot(three + timedelta(hours=2, minutes=15))
    assert after["T1"]["slot_status"] == "AVAILABLE" and after["T1"]["available"] is True

    small = slot(three + timedelta(hours=6))
    party6 = w.client.get(
        "/api/v1/admin/reservations/availability", headers=w.ah,
        params={"restaurant_id": w.rid, "starts_at": _iso(three + timedelta(hours=6)), "party_size": 6},
    ).json()["tables"]
    assert {t["table_number"]: t["slot_status"] for t in party6}["T1"] == "TOO_SMALL"
    assert small["T3"]["available"] is True


def test_complete_early_frees_remaining_window(world):
    w = world
    start = _now() - timedelta(minutes=10)
    res = w.client.post(
        f"/api/v1/admin/reservations?restaurant_id={w.rid}", headers=w.ah,
        json={"table_id": w.t1.id, "party_size": 2, "starts_at": _iso(start), "guest_name": "Early", "seat_immediately": True, "duration_minutes": 120},
    ).json()
    w.client.patch(f"/api/v1/admin/reservations/{res['id']}/status?restaurant_id={w.rid}", headers=w.ah, json={"status": "COMPLETED"})
    # Table can now be booked an hour from now even though the original 2h window would have covered it.
    again = _book(w, w.t1, _now() + timedelta(hours=1))
    assert again.status_code == 201, again.text


def test_invalid_status_transition_rejected(world):
    w = world
    res = _book(w, w.t1, _now() + timedelta(hours=5)).json()
    path = f"/api/v1/admin/reservations/{res['id']}/status?restaurant_id={w.rid}"
    assert w.client.patch(path, headers=w.ah, json={"status": "CANCELLED"}).status_code == 200
    assert w.client.patch(path, headers=w.ah, json={"status": "SEATED"}).status_code == 400


def test_seating_too_early_rejected_and_seating_shifts_start(world):
    w = world
    far = _book(w, w.t1, _now() + timedelta(hours=5)).json()
    r = w.client.patch(f"/api/v1/admin/reservations/{far['id']}/status?restaurant_id={w.rid}", headers=w.ah, json={"status": "SEATED"})
    assert r.status_code == 400

    near = _book(w, w.t2, _now() + timedelta(minutes=20)).json()
    r = w.client.patch(f"/api/v1/admin/reservations/{near['id']}/status?restaurant_id={w.rid}", headers=w.ah, json={"status": "SEATED"})
    assert r.status_code == 200, r.text
    assert _table_status(w, w.t2)["status"] == "OCCUPIED"


def test_admin_can_reschedule_and_move_table(world):
    w = world
    res = _book(w, w.t1, _now() + timedelta(hours=4)).json()
    new_start = _now() + timedelta(hours=6)
    r = w.client.patch(
        f"/api/v1/admin/reservations/{res['id']}?restaurant_id={w.rid}", headers=w.ah,
        json={"table_id": w.t2.id, "starts_at": _iso(new_start), "duration_minutes": 60},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["table_id"] == w.t2.id and body["table_number"] == "T2"
    assert datetime.fromisoformat(body["ends_at"]) - datetime.fromisoformat(body["starts_at"]) == timedelta(minutes=60)

    # Old slot is free again, new one is taken.
    assert _book(w, w.t1, _now() + timedelta(hours=4)).status_code == 201
    other = w.client.post(
        f"/api/v1/admin/reservations?restaurant_id={w.rid}", headers=w.ah,
        json={"table_id": w.t2.id, "party_size": 2, "starts_at": _iso(new_start + timedelta(hours=2)), "guest_name": "Later"},
    )
    assert other.status_code == 201, other.text
    # Moving onto the later booking's time must be refused; the reservation itself is not a conflict.
    clash = w.client.patch(
        f"/api/v1/admin/reservations/{res['id']}?restaurant_id={w.rid}", headers=w.ah,
        json={"starts_at": _iso(new_start + timedelta(hours=1, minutes=30))},
    )
    assert clash.status_code == 400
    # Overlap with itself must not count as a conflict when moving within its own window.
    r = w.client.patch(
        f"/api/v1/admin/reservations/{res['id']}?restaurant_id={w.rid}", headers=w.ah,
        json={"starts_at": _iso(new_start + timedelta(minutes=15))},
    )
    assert r.status_code == 200, r.text


def test_customer_cannot_double_book_same_time(world):
    w = world
    start = _now() + timedelta(hours=3)
    assert _book(w, w.t1, start).status_code == 201
    second = _book(w, w.t2, start + timedelta(minutes=30))
    assert second.status_code == 400
    assert "already have a reservation" in second.json()["detail"]


def test_booking_window_limits(world):
    w = world
    assert _book(w, w.t1, _now() - timedelta(hours=1)).status_code == 400
    assert _book(w, w.t1, _now() + timedelta(days=200)).status_code == 400


def test_availability_suggests_alternative_times(world):
    w = world
    start = _now() + timedelta(hours=3)
    for t in (w.t1, w.t2, w.t3):  # a party of 2 fits every table; block them all (walk-in style, no user)
        r = w.client.post(
            f"/api/v1/admin/reservations?restaurant_id={w.rid}", headers=w.ah,
            json={"table_id": t.id, "party_size": 2, "starts_at": _iso(start), "guest_name": "Blocker"},
        )
        assert r.status_code == 201, r.text
    r = w.client.get(
        f"/api/v1/restaurants/{w.restaurant.slug}/reservations/availability",
        params={"starts_at": _iso(start), "party_size": 2},
    ).json()
    assert r["tables"] == []
    assert r["suggested_times"], "expected alternative slots"


def test_stale_confirmed_reservation_is_closed(world):
    w = world
    past = _now() - timedelta(hours=5)
    row = Reservation(
        restaurant_id=w.rid, table_id=w.t1.id, user_id=w.customer.id, party_size=2,
        starts_at=past, ends_at=past + timedelta(minutes=90), status=ReservationStatus.CONFIRMED, guest_name="No Show",
    )
    w.db.add(row)
    w.db.flush()
    mine = w.client.get("/api/v1/reservations/me", headers=w.ch).json()
    assert all(r["id"] != row.id for r in mine)
    hist = w.client.get("/api/v1/reservations/me?include_past=true", headers=w.ch).json()
    assert next(r for r in hist if r["id"] == row.id)["status"] == "EXPIRED"


def test_customer_cancel_frees_table(world):
    w = world
    res = _book(w, w.t1, _now() + timedelta(minutes=30)).json()
    assert _table_status(w, w.t1)["status"] == "RESERVED"
    assert w.client.post(f"/api/v1/reservations/{res['id']}/cancel", headers=w.ch).status_code == 200
    assert _table_status(w, w.t1)["status"] == "AVAILABLE"


def test_tables_view_lists_reservations(world):
    w = world
    _book(w, w.t1, _now() + timedelta(hours=3))
    row = _table_status(w, w.t1)
    assert row["reservations"] and row["reservations"][0]["guest_name"] == "Guest"
    assert row["reservations"][0]["blocking"] is False


# --------------------------------------------------------------------------- overstay / back-to-back

def _seated_overdue(w, table, *, over_minutes=30, name="Old Party", user=None):
    """A party seated for a booking that already ended `over_minutes` ago, never checked out."""
    now = _now()
    r = Reservation(
        restaurant_id=w.rid, table_id=table.id, user_id=user.id if user else None, party_size=2, guest_name=name,
        starts_at=now - timedelta(minutes=over_minutes + 120), ends_at=now - timedelta(minutes=over_minutes),
        status=ReservationStatus.SEATED,
    )
    w.db.add(r)
    w.db.flush()
    w.db.get(RestaurantTable, table.id).status = TableStatus.OCCUPIED
    w.db.flush()
    return r


def _admin_book(w, table, starts, minutes=90, name="Guest", **extra):
    return w.client.post(
        f"/api/v1/admin/reservations?restaurant_id={w.rid}", headers=w.ah,
        json={"table_id": table.id, "party_size": 2, "starts_at": _iso(starts), "duration_minutes": minutes,
              "guest_name": name, **extra},
    )


def _status(w, rid, status):
    return w.client.patch(f"/api/v1/admin/reservations/{rid}/status?restaurant_id={w.rid}", headers=w.ah, json={"status": status})


def test_back_to_back_bookings_respect_turnover_buffer(world):
    w = world
    start = _now() + timedelta(hours=3)
    assert _admin_book(w, w.t1, start, 120, "First").status_code == 201          # 3h..5h
    assert _admin_book(w, w.t1, start + timedelta(hours=2), 120, "Second").status_code == 400   # exactly 5h: no gap
    assert _admin_book(w, w.t1, start + timedelta(hours=2, minutes=15), 120, "Second").status_code == 201


def test_buffer_is_a_per_restaurant_setting(world):
    w = world
    r = w.client.patch(f"/api/v1/admin/settings?restaurant_id={w.rid}", headers=w.ah, json={"reservation_buffer_minutes": 0})
    assert r.status_code == 200 and r.json()["reservation_buffer_minutes"] == 0
    start = _now() + timedelta(hours=3)
    assert _admin_book(w, w.t1, start, 120, "First").status_code == 201
    assert _admin_book(w, w.t1, start + timedelta(hours=2), 120, "Second").status_code == 201  # back-to-back allowed
    bad = w.client.patch(f"/api/v1/admin/settings?restaurant_id={w.rid}", headers=w.ah, json={"reservation_buffer_minutes": 999})
    assert bad.status_code == 422


def test_cannot_seat_new_party_on_top_of_seated_guests(world):
    w = world
    old = _seated_overdue(w, w.t1)
    nxt = _admin_book(w, w.t1, _now() + timedelta(minutes=45), 90, "Next Party").json()
    r = _status(w, nxt["id"], "SEATED")
    assert r.status_code == 400 and "still has seated guests" in r.json()["detail"]
    # walk-in on the same table is refused too
    walk = _admin_book(w, w.t1, _now(), 60, "Walk", seat_immediately=True)
    assert walk.status_code == 400

    assert _status(w, old.id, "COMPLETED").status_code == 200
    assert _status(w, nxt["id"], "SEATED").status_code == 200


def test_overdue_and_blocked_by_are_reported(world):
    w = world
    nxt = _admin_book(w, w.t1, _now() + timedelta(minutes=10), 90, "Next Party").json()   # due very soon
    later = _admin_book(w, w.t2, _now() + timedelta(hours=3), 90, "Much Later").json()
    _seated_overdue(w, w.t1, over_minutes=25)   # ...but the previous party never left

    rows = w.client.get(f"/api/v1/admin/reservations?restaurant_id={w.rid}", headers=w.ah).json()
    by_id = {r["id"]: r for r in rows}
    old = next(r for r in rows if r["guest_name"] == "Old Party")
    assert 24 <= old["overdue_minutes"] <= 26
    assert by_id[nxt["id"]]["blocked_by"] == "Old Party"      # due, and their table is still occupied
    assert by_id[later["id"]]["blocked_by"] is None            # not due yet / different table

    tables = w.client.get(f"/api/v1/admin/tables?restaurant_id={w.rid}", headers=w.ah).json()
    brief = next(t for t in tables if t["id"] == w.t1.id)["reservations"]
    assert next(b for b in brief if b["guest_name"] == "Old Party")["overdue_minutes"] >= 24

    # Once the old party is checked out the warning disappears.
    _status(w, old["id"], "COMPLETED")
    rows = w.client.get(f"/api/v1/admin/reservations?restaurant_id={w.rid}", headers=w.ah).json()
    assert next(r for r in rows if r["id"] == nxt["id"])["blocked_by"] is None


def test_extend_gives_more_time_from_now_when_overdue(world):
    w = world
    old = _seated_overdue(w, w.t1, over_minutes=30)
    r = w.client.post(f"/api/v1/admin/reservations/{old.id}/extend?restaurant_id={w.rid}", headers=w.ah, json={"minutes": 30})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["overdue_minutes"] == 0
    remaining = datetime.fromisoformat(body["ends_at"]) - datetime.now(timezone.utc)
    assert timedelta(minutes=29) <= remaining <= timedelta(minutes=31)   # extended from now, not from the stale end
    assert _table_status(w, w.t1)["status"] == "OCCUPIED"


def test_extend_refused_when_next_booking_would_clash(world):
    w = world
    old = _seated_overdue(w, w.t1, over_minutes=10)
    _admin_book(w, w.t1, _now() + timedelta(minutes=30), 90, "Bob")
    r = w.client.post(f"/api/v1/admin/reservations/{old.id}/extend?restaurant_id={w.rid}", headers=w.ah, json={"minutes": 30})
    assert r.status_code == 400
    assert "Bob" in r.json()["detail"] and "Move that booking" in r.json()["detail"]

    # A short extension that still leaves the buffer before Bob is fine.
    ok = w.client.post(f"/api/v1/admin/reservations/{old.id}/extend?restaurant_id={w.rid}", headers=w.ah, json={"minutes": 5})
    assert ok.status_code == 200, ok.text


def test_extend_only_for_seated_and_capped(world):
    w = world
    res = _admin_book(w, w.t1, _now() + timedelta(hours=3)).json()
    assert w.client.post(f"/api/v1/admin/reservations/{res['id']}/extend?restaurant_id={w.rid}",
                         headers=w.ah, json={"minutes": 30}).status_code == 400
    old = _seated_overdue(w, w.t2, over_minutes=0)
    for _ in range(8):  # keep stretching; total length is capped at 8 hours
        r = w.client.post(f"/api/v1/admin/reservations/{old.id}/extend?restaurant_id={w.rid}", headers=w.ah, json={"minutes": 120})
        if r.status_code != 200:
            break
    assert r.status_code == 400 and "longer than" in r.json()["detail"]


def test_forgotten_checkout_is_closed_automatically(world):
    w = world
    _seated_overdue(w, w.t1, over_minutes=45)
    assert _table_status(w, w.t1)["status"] == "OCCUPIED"            # overdue, but might still be there
    stale = _seated_overdue(w, w.t2, over_minutes=90, name="Ghost Party")
    tables = w.client.get(f"/api/v1/admin/tables?restaurant_id={w.rid}", headers=w.ah).json()
    assert next(t for t in tables if t["id"] == w.t2.id)["status"] == "AVAILABLE"
    rows = w.client.get(f"/api/v1/admin/reservations?restaurant_id={w.rid}", headers=w.ah).json()
    assert next(r for r in rows if r["id"] == stale.id)["status"] == "COMPLETED"
    assert next(r for r in rows if r["guest_name"] == "Old Party")["status"] == "SEATED"


def test_availability_names_the_overstaying_party(world):
    w = world
    _seated_overdue(w, w.t1, over_minutes=30)
    r = w.client.get(
        "/api/v1/admin/reservations/availability", headers=w.ah,
        params={"restaurant_id": w.rid, "starts_at": _iso(_now() + timedelta(minutes=5)), "party_size": 2},
    ).json()
    t1 = next(t for t in r["tables"] if t["table_number"] == "T1")
    assert t1["slot_status"] == "OCCUPIED" and t1["available"] is False
    assert [c["guest_name"] for c in t1["conflicts"]] == ["Old Party"]
