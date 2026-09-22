"""Confirm/cancel a reservation straight from an emailed link — no account needed."""

import re
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.core.security import create_reservation_action_token, decode_reservation_action_token
from app.models.enums import ReservationStatus
from app.models.reservation import Reservation
from tests.test_reservation_flows import _admin_book, _book, _now, world  # noqa: F401  (world is a fixture)

API = "/api/v1"


def queued(db, subject_contains=None):
    rows = db.execute(text("SELECT id, payload, run_at, status FROM jobs WHERE type = 'send_email' ORDER BY id")).all()
    return [r for r in rows if subject_contains is None or subject_contains in r.payload["subject"]]


def manage_link(db, subject_contains):
    [mail] = queued(db, subject_contains)
    return re.search(r"https?://\S+/reservations/manage\?token=\S+", mail.payload["text"]).group(0)


def token_from(link: str) -> str:
    return link.split("token=", 1)[1]


# ------------------------------------------------------------------ the link itself

def test_the_confirmation_email_carries_a_working_link(world):
    w = world
    res = _book(w, w.t1, _now() + timedelta(hours=5)).json()
    link = manage_link(w.db, "is booked")
    assert "/reservations/manage?token=" in link
    r = w.client.get(f"{API}/reservations/actions/{token_from(link)}")
    assert r.status_code == 200 and r.json()["id"] == res["id"]


def test_the_reminder_email_also_carries_a_link(world):
    w = world
    _book(w, w.t1, _now() + timedelta(hours=10))
    link = manage_link(w.db, "See you soon")
    r = w.client.get(f"{API}/reservations/actions/{token_from(link)}")
    assert r.status_code == 200


def test_a_walk_in_or_unemailed_booking_gets_no_link(world):
    w = world
    _admin_book(w, w.t1, _now(), name="Walk In", seat_immediately=True)
    assert queued(w.db) == []


# ------------------------------------------------------------------ using the link

def test_confirming_attendance_sets_a_timestamp_staff_can_see(world):
    w = world
    res = _book(w, w.t1, _now() + timedelta(hours=5)).json()
    token = token_from(manage_link(w.db, "is booked"))
    assert res.get("guest_confirmed_at") is None

    r = w.client.post(f"{API}/reservations/actions/{token}/confirm")
    assert r.status_code == 200 and r.json()["guest_confirmed_at"] is not None

    staff_view = w.client.get(f"{API}/admin/reservations", params={"restaurant_id": w.rid}, headers=w.ah).json()
    seen = next(x for x in staff_view if x["id"] == res["id"])
    assert seen["guest_confirmed_at"] is not None


def test_confirming_twice_is_harmless(world):
    w = world
    _book(w, w.t1, _now() + timedelta(hours=5))
    token = token_from(manage_link(w.db, "is booked"))
    first = w.client.post(f"{API}/reservations/actions/{token}/confirm").json()["guest_confirmed_at"]
    second = w.client.post(f"{API}/reservations/actions/{token}/confirm").json()["guest_confirmed_at"]
    assert second >= first


def test_cancelling_by_link_works_like_cancelling_while_signed_in(world):
    w = world
    res = _book(w, w.t1, _now() + timedelta(hours=5)).json()
    token = token_from(manage_link(w.db, "is booked"))

    r = w.client.post(f"{API}/reservations/actions/{token}/cancel")
    assert r.status_code == 200 and r.json()["status"] == "CANCELLED"
    assert len(queued(w.db, "was cancelled")) == 1

    reservation = w.db.get(Reservation, res["id"])
    assert reservation.status == ReservationStatus.CANCELLED


def test_a_link_cannot_be_used_after_the_reservation_is_gone(world):
    w = world
    res = _book(w, w.t1, _now() + timedelta(hours=5)).json()
    token = token_from(manage_link(w.db, "is booked"))
    w.client.post(f"{API}/reservations/actions/{token}/cancel")

    again = w.client.post(f"{API}/reservations/actions/{token}/cancel")
    assert again.status_code == 400
    still_cancelled = w.db.get(Reservation, res["id"])
    assert still_cancelled.status == ReservationStatus.CANCELLED  # unchanged, not reopened


def test_cancelling_a_booking_with_an_order_attached_is_refused_by_link_too(world):
    from decimal import Decimal

    from app.models.enums import OrderStatus, OrderType
    from app.models.order import Order

    w = world
    res = _book(w, w.t1, _now() + timedelta(hours=5)).json()
    token = token_from(manage_link(w.db, "is booked"))
    order = Order(
        restaurant_id=w.rid, order_number="X-1", order_type=OrderType.DINE_IN, status=OrderStatus.CONFIRMED,
        subtotal=Decimal("1"), tax=Decimal("0"), delivery_fee=Decimal("0"), discount=Decimal("0"), total=Decimal("1"),
        customer_name="Guest", customer_email="rf-cust@demo.com", table_id=w.t1.id,
    )
    w.db.add(order)
    w.db.flush()
    reservation = w.db.get(Reservation, res["id"])
    reservation.order_id = order.id
    w.db.flush()

    r = w.client.post(f"{API}/reservations/actions/{token}/cancel")
    assert r.status_code == 400 and "contact the restaurant" in r.json()["detail"]


# ------------------------------------------------------------------ tokens cannot be forged or misused

def test_an_unsigned_or_garbage_token_is_refused(world):
    w = world
    for bad in ("not-a-token", "a.b.c", ""):
        assert w.client.get(f"{API}/reservations/actions/{bad or 'x'}").status_code == 400


def test_a_token_for_a_different_reservation_or_restaurant_does_not_work(world):
    w = world
    res = _book(w, w.t1, _now() + timedelta(hours=5)).json()
    wrong_id = create_reservation_action_token(res["id"] + 999999, w.rid, datetime.now(timezone.utc) + timedelta(hours=1))
    assert w.client.get(f"{API}/reservations/actions/{wrong_id}").status_code == 404
    wrong_restaurant = create_reservation_action_token(res["id"], w.rid + 999999, datetime.now(timezone.utc) + timedelta(hours=1))
    assert w.client.get(f"{API}/reservations/actions/{wrong_restaurant}").status_code == 404


def test_an_expired_token_is_refused(world):
    w = world
    res = _book(w, w.t1, _now() + timedelta(hours=5)).json()
    expired = create_reservation_action_token(res["id"], w.rid, datetime.now(timezone.utc) - timedelta(minutes=1))
    r = w.client.get(f"{API}/reservations/actions/{expired}")
    assert r.status_code == 400 and "expired" in r.json()["detail"].lower()


def test_a_token_signed_as_an_account_token_does_not_work_here(world):
    from app.core.security import create_access_token
    w = world
    _book(w, w.t1, _now() + timedelta(hours=5))
    forged = create_access_token(str(w.customer.id), claims={"role": "CUSTOMER"})
    assert w.client.get(f"{API}/reservations/actions/{forged}").status_code == 400


def test_the_token_type_is_exactly_reservation_action():
    with pytest.raises(ValueError):
        decode_reservation_action_token("garbage")
