"""Ordering ahead for a collection slot, and the capacity controls that can turn an order away.

Dates are always taken relative to the restaurant's own clock, and the scheduling tests use
*tomorrow* so a full day of slots exists however late in the day the suite happens to run.
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from app.db.session import get_db
from app.main import app
from app.models.category import Category
from app.models.enums import OrderStatus, OrderType, RoleName
from app.models.menu_item import MenuItem
from app.models.order import Order
from app.models.restaurant import Restaurant
from app.models.restaurant_user import RestaurantUser
from app.services.feature_service import FeatureService
from app.services.scheduling_service import SchedulingService
from tests.conftest import override_get_db
from tests.tenants import header, make_user

API = "/api/v1"
ALL_DAY = {day: "00:00-23:59" for day in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")}


@pytest.fixture
def world(client, db):
    app.dependency_overrides[get_db] = override_get_db(db)
    restaurant = Restaurant(
        name="Slot Kitchen", slug="slot-kitchen", tax_rate=Decimal("0.10"), delivery_fee=Decimal("2"),
        pickup_enabled=True, dine_in_enabled=True, timezone="UTC", opening_hours=ALL_DAY,
        slot_interval_minutes=30, scheduled_order_days_ahead=7, scheduled_order_lead_minutes=30,
    )
    db.add(restaurant)
    db.flush()
    admin = make_user(db, "slot-admin@iso-demo.com", RoleName.RESTAURANT_ADMIN)
    staff = make_user(db, "slot-staff@iso-demo.com", RoleName.RESTAURANT_STAFF)
    customer = make_user(db, "slot-cust@iso-demo.com", RoleName.CUSTOMER, restaurant_id=restaurant.id)
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

    FeatureService(db).set(restaurant.id, "scheduled_orders", True, admin)
    db.commit()
    db.expire_all()

    yield type("W", (), {
        "client": client, "db": db, "rid": restaurant.id, "restaurant": restaurant, "admin": admin,
        "staff": staff, "customer": customer, "item": item,
    })
    app.dependency_overrides.clear()


def tomorrow() -> date:
    return datetime.now(UTC).date() + timedelta(days=1)


def slots_on(w, on: date):
    r = w.client.get(f"{API}/restaurants/{w.restaurant.slug}/pickup-slots?on={on.isoformat()}")
    assert r.status_code == 200, r.text
    return r.json()


def order(w, *, scheduled_for=None, order_type="PICKUP", user=None, reservation_id=None):
    body = {
        "restaurant_id": w.rid, "order_type": order_type, "customer_name": "Slot Customer",
        "customer_email": (user or w.customer).email,
        "items": [{"menu_item_id": w.item.id, "quantity": 1, "modifier_option_ids": []}],
    }
    if scheduled_for is not None:
        body["scheduled_for"] = scheduled_for
    if reservation_id is not None:
        body["reservation_id"] = reservation_id
    return w.client.post(f"{API}/orders", headers=header(user or w.customer), json=body)


# ------------------------------------------------------------------ the slot grid

def test_slots_come_from_the_opening_hours_at_the_configured_interval(world):
    w = world
    body = slots_on(w, tomorrow())
    times = [s["at"] for s in body["slots"]]
    assert body["interval_minutes"] == 30 and body["timezone"] == "UTC"
    # 00:00 .. 23:00 — a slot has to *finish* by closing time, so with a 23:59 close the 23:30 slot
    # (which would run to 00:00) is not offered.
    assert len(times) == 47
    assert times[0].endswith("T00:00:00Z") and times[-1].endswith("T23:00:00Z")
    assert times == sorted(times)


def test_a_closed_day_has_no_slots(world):
    w = world
    w.restaurant.opening_hours = {**ALL_DAY, tomorrow().strftime("%A").lower(): "closed"}
    w.db.commit()
    assert slots_on(w, tomorrow())["slots"] == []


def test_a_closure_day_has_no_slots(world):
    w = world
    w.restaurant.closures = [{"date": tomorrow().isoformat(), "label": "Staff party"}]
    w.db.commit()
    assert slots_on(w, tomorrow())["slots"] == []


def test_slots_stop_at_the_days_ahead_limit(world):
    w = world
    assert slots_on(w, date.today() + timedelta(days=7))["slots"] != []
    assert slots_on(w, date.today() + timedelta(days=8))["slots"] == []
    assert slots_on(w, date.today() - timedelta(days=1))["slots"] == []


def test_slots_sooner_than_the_kitchens_lead_time_are_not_offered(world):
    w = world
    svc = SchedulingService(w.db)
    # Pretend it is 12:00 tomorrow: with a 30-minute lead, 12:00 and 12:15 are gone but 12:30 stands.
    noon = datetime.combine(tomorrow(), datetime.min.time(), tzinfo=UTC) + timedelta(hours=12)
    offered = [s.at for s in svc.available_slots(w.restaurant, tomorrow(), now=noon)]
    assert noon not in offered
    assert noon + timedelta(minutes=30) in offered


def test_a_full_slot_drops_out_and_remaining_counts_down(world):
    w = world
    w.restaurant.max_orders_per_slot = 1
    w.db.commit()

    first = slots_on(w, tomorrow())["slots"][0]
    assert first["remaining"] == 1
    assert order(w, scheduled_for=first["at"]).status_code == 201

    after = slots_on(w, tomorrow())["slots"]
    assert first["at"] not in [s["at"] for s in after]  # that slot is used up


def test_the_flag_gates_the_slots_endpoint(world):
    w = world
    FeatureService(w.db).set(w.rid, "scheduled_orders", False, w.admin)
    w.db.commit()
    r = w.client.get(f"{API}/restaurants/{w.restaurant.slug}/pickup-slots")
    assert r.status_code == 403


# ------------------------------------------------------------------ ordering ahead

def test_ordering_ahead_stores_the_chosen_slot(world):
    w = world
    slot = slots_on(w, tomorrow())["slots"][10]["at"]
    r = order(w, scheduled_for=slot)
    assert r.status_code == 201, r.text
    assert r.json()["scheduled_for"] is not None
    saved = w.db.get(Order, r.json()["id"])
    assert saved.scheduled_for == datetime.fromisoformat(slot)


def test_an_order_for_now_still_has_no_slot(world):
    w = world
    r = order(w)
    assert r.status_code == 201 and r.json()["scheduled_for"] is None


def test_a_slot_that_is_not_on_the_grid_is_refused(world):
    w = world
    grid_slot = datetime.fromisoformat(slots_on(w, tomorrow())["slots"][5]["at"])
    off_grid = (grid_slot + timedelta(minutes=7)).isoformat()   # between two slots
    in_the_past = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
    too_far = (datetime.now(UTC) + timedelta(days=30)).isoformat()
    for bad in (off_grid, in_the_past, too_far):
        r = order(w, scheduled_for=bad)
        assert r.status_code == 400, f"{bad} should have been refused, got {r.status_code}"


def test_you_can_order_ahead_even_while_the_restaurant_is_closed_right_now(world):
    w = world
    # Shut today with a closure: ordering now is impossible, but tomorrow's slots must still work.
    w.restaurant.closures = [{"date": datetime.now(UTC).date().isoformat(), "label": "Closed today"}]
    w.db.commit()

    assert order(w).status_code == 400  # nothing doing right now
    slot = slots_on(w, tomorrow())["slots"][10]["at"]
    assert order(w, scheduled_for=slot).status_code == 201


def test_the_flag_gates_ordering_ahead(world):
    w = world
    slot = slots_on(w, tomorrow())["slots"][10]["at"]
    FeatureService(w.db).set(w.rid, "scheduled_orders", False, w.admin)
    w.db.commit()
    r = order(w, scheduled_for=slot)
    assert r.status_code == 400 and "not available" in r.json()["detail"].lower()


def test_a_dine_in_order_cannot_be_scheduled_separately(world):
    w = world
    slot = slots_on(w, tomorrow())["slots"][10]["at"]
    r = order(w, scheduled_for=slot, order_type="DINE_IN")
    assert r.status_code == 400 and "booking time" in r.json()["detail"].lower()


# ------------------------------------------------------------------ capacity controls

def test_pausing_online_ordering_turns_customers_away_with_the_reason(world):
    w = world
    w.restaurant.online_ordering_paused = True
    w.restaurant.ordering_pause_reason = "we're out of dough"
    w.db.commit()

    r = order(w)
    assert r.status_code == 400 and "out of dough" in r.json()["detail"]
    # A pause means a pause: pre-orders stop too.
    slot = slots_on(w, tomorrow())["slots"][10]["at"]
    assert order(w, scheduled_for=slot).status_code == 400


def test_a_busy_kitchen_stops_taking_orders_but_still_takes_pre_orders(world):
    w = world
    w.restaurant.max_pending_orders = 1
    w.db.commit()

    assert order(w).status_code == 201          # the queue now holds one
    busy = order(w)
    assert busy.status_code == 400 and "capacity" in busy.json()["detail"].lower()

    # An order for a later slot isn't in today's queue, so it is still welcome.
    slot = slots_on(w, tomorrow())["slots"][10]["at"]
    assert order(w, scheduled_for=slot).status_code == 201


def test_a_completed_order_frees_the_queue_again(world):
    w = world
    w.restaurant.max_pending_orders = 1
    w.db.commit()
    first = order(w).json()["id"]
    assert order(w).status_code == 400

    placed = w.db.get(Order, first)
    placed.status = OrderStatus.COMPLETED
    w.db.commit()
    assert order(w).status_code == 201


# ------------------------------------------------------------------ the kitchen screen

def _confirmed_order(w, scheduled_for):
    """A CONFIRMED order straight into the database, so the kitchen query can be tested on its own."""
    row = Order(
        restaurant_id=w.rid, user_id=w.customer.id, order_number=f"SK-{scheduled_for:%H%M%S}",
        order_type=OrderType.PICKUP, status=OrderStatus.CONFIRMED, subtotal=Decimal("10"),
        tax=Decimal("1"), total=Decimal("11"), customer_name="Slot Customer", scheduled_for=scheduled_for,
    )
    w.db.add(row)
    w.db.commit()
    return row


def test_the_kitchen_only_sees_a_scheduled_order_once_it_is_nearly_due(world):
    w = world
    due_soon = _confirmed_order(w, datetime.now(UTC) + timedelta(minutes=10))   # inside the 30-min lead
    later = _confirmed_order(w, datetime.now(UTC) + timedelta(hours=8))         # well outside it

    board = w.client.get(f"{API}/admin/kitchen?restaurant_id={w.rid}", headers=header(w.staff)).json()
    showing = [o["id"] for o in board["new_orders"]]
    assert due_soon.id in showing
    assert later.id not in showing


def test_a_scheduled_order_staff_have_started_stays_on_the_board(world):
    w = world
    early_start = _confirmed_order(w, datetime.now(UTC) + timedelta(hours=8))
    early_start.status = OrderStatus.PREPARING  # someone decided to get ahead
    w.db.commit()

    board = w.client.get(f"{API}/admin/kitchen?restaurant_id={w.rid}", headers=header(w.staff)).json()
    assert early_start.id in [o["id"] for o in board["preparing"]]
