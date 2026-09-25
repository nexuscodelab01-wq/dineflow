"""Guest reviews: eligibility, submission, public display, and staff moderation/reply."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.db.session import get_db
from app.main import app
from app.models.enums import OrderStatus, OrderType, ReservationStatus, RoleName, TableStatus
from app.models.order import Order
from app.models.reservation import Reservation
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
        name="Review House", slug="review-house", tax_rate=Decimal("0.1"), delivery_fee=Decimal("2"),
        dine_in_enabled=True, timezone="UTC",
    )
    db.add(restaurant)
    db.flush()
    admin = make_user(db, "review-admin@iso-demo.com", RoleName.RESTAURANT_ADMIN)
    staff = make_user(db, "review-staff@iso-demo.com", RoleName.RESTAURANT_STAFF)
    customer = make_user(db, "review-cust@iso-demo.com", RoleName.CUSTOMER, restaurant_id=restaurant.id)
    other_customer = make_user(db, "review-other@iso-demo.com", RoleName.CUSTOMER, restaurant_id=restaurant.id)
    db.add_all([RestaurantUser(restaurant_id=restaurant.id, user_id=admin.id, role=RoleName.RESTAURANT_ADMIN), RestaurantUser(restaurant_id=restaurant.id, user_id=staff.id, role=RoleName.RESTAURANT_STAFF)])
    table = RestaurantTable(restaurant_id=restaurant.id, table_number="R1", capacity=4, status=TableStatus.AVAILABLE)
    db.add(table)
    db.flush()

    order = Order(
        restaurant_id=restaurant.id, user_id=customer.id, order_number="RH-1", order_type=OrderType.PICKUP,
        status=OrderStatus.COMPLETED, subtotal=Decimal("20.00"), tax=Decimal("2.00"), total=Decimal("22.00"),
        customer_name="Review Customer", customer_email=customer.email,
    )
    pending_order = Order(
        restaurant_id=restaurant.id, user_id=customer.id, order_number="RH-2", order_type=OrderType.PICKUP,
        status=OrderStatus.PENDING, subtotal=Decimal("10.00"), tax=Decimal("1.00"), total=Decimal("11.00"),
        customer_name="Review Customer", customer_email=customer.email,
    )
    start = datetime.now(timezone.utc) - timedelta(days=1)
    reservation = Reservation(
        restaurant_id=restaurant.id, table_id=table.id, user_id=customer.id, party_size=2, guest_name="Review Customer",
        starts_at=start, ends_at=start + timedelta(minutes=90), status=ReservationStatus.COMPLETED,
    )
    db.add_all([order, pending_order, reservation])
    db.flush()

    FeatureService(db).set(restaurant.id, "reviews", True, admin)
    db.commit()
    db.expire_all()

    yield type("W", (), {
        "client": client, "db": db, "rid": restaurant.id, "restaurant": restaurant, "admin": admin, "staff": staff,
        "customer": customer, "other_customer": other_customer, "order": order, "pending_order": pending_order,
        "reservation": reservation,
    })
    app.dependency_overrides.clear()


# ------------------------------------------------------------------ eligibility

def test_eligible_visits_lists_completed_order_and_reservation_but_not_pending(world):
    w = world
    r = w.client.get(f"{API}/reviews/eligible", headers=header(w.customer))
    assert r.status_code == 200, r.text
    visits = r.json()
    assert {v["order_id"] for v in visits if v["order_id"]} == {w.order.id}
    assert {v["reservation_id"] for v in visits if v["reservation_id"]} == {w.reservation.id}


def test_a_customer_with_no_visits_has_nothing_eligible(world):
    w = world
    r = w.client.get(f"{API}/reviews/eligible", headers=header(w.other_customer))
    assert r.status_code == 200 and r.json() == []


def test_the_flag_gates_the_whole_feature(world):
    w = world
    FeatureService(w.db).set(w.rid, "reviews", False, w.admin)
    w.db.commit()
    assert w.client.get(f"{API}/reviews/eligible", headers=header(w.customer)).status_code == 403
    assert w.client.get(f"{API}/restaurants/{w.restaurant.slug}/reviews").status_code == 403


# ------------------------------------------------------------------ submitting

def test_submitting_a_review_for_a_completed_order(world):
    w = world
    r = w.client.post(f"{API}/reviews", headers=header(w.customer), json={"order_id": w.order.id, "rating": 5, "comment": "Loved it"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["rating"] == 5 and body["comment"] == "Loved it" and body["is_published"] is True

    mine = w.client.get(f"{API}/reviews", headers=header(w.customer)).json()
    assert len(mine) == 1 and mine[0]["order_id"] == w.order.id


def test_resubmitting_the_same_visit_edits_it_instead_of_erroring(world):
    w = world
    w.client.post(f"{API}/reviews", headers=header(w.customer), json={"order_id": w.order.id, "rating": 3, "comment": "Okay"})
    r = w.client.post(f"{API}/reviews", headers=header(w.customer), json={"order_id": w.order.id, "rating": 5, "comment": "Actually great"})
    assert r.status_code == 201, r.text
    mine = w.client.get(f"{API}/reviews", headers=header(w.customer)).json()
    assert len(mine) == 1 and mine[0]["rating"] == 5 and mine[0]["comment"] == "Actually great"


def test_a_pending_order_cannot_be_reviewed(world):
    w = world
    r = w.client.post(f"{API}/reviews", headers=header(w.customer), json={"order_id": w.pending_order.id, "rating": 4})
    assert r.status_code == 400


def test_a_customer_cannot_review_someone_elses_order(world):
    w = world
    r = w.client.post(f"{API}/reviews", headers=header(w.other_customer), json={"order_id": w.order.id, "rating": 1})
    assert r.status_code == 404


def test_exactly_one_of_order_or_reservation_is_required(world):
    w = world
    assert w.client.post(f"{API}/reviews", headers=header(w.customer), json={"rating": 4}).status_code == 422
    assert w.client.post(
        f"{API}/reviews", headers=header(w.customer),
        json={"order_id": w.order.id, "reservation_id": w.reservation.id, "rating": 4},
    ).status_code == 422


def test_rating_must_be_in_range(world):
    w = world
    assert w.client.post(f"{API}/reviews", headers=header(w.customer), json={"order_id": w.order.id, "rating": 0}).status_code == 422
    assert w.client.post(f"{API}/reviews", headers=header(w.customer), json={"order_id": w.order.id, "rating": 6}).status_code == 422


# ------------------------------------------------------------------ public display

def test_published_reviews_are_public_with_first_name_and_last_initial_only(world):
    w = world
    w.client.post(f"{API}/reviews", headers=header(w.customer), json={"order_id": w.order.id, "rating": 4, "comment": "Great food"})
    r = w.client.get(f"{API}/restaurants/{w.restaurant.slug}/reviews")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 1 and body["average_rating"] == 4.0
    [review] = body["items"]
    assert review["comment"] == "Great food" and review["reviewer_name"] == "Test U."
    assert "reviewer_email" not in review


def test_a_hidden_review_never_appears_publicly(world):
    w = world
    review_id = w.client.post(f"{API}/reviews", headers=header(w.customer), json={"order_id": w.order.id, "rating": 2}).json()["id"]
    w.client.post(f"{API}/admin/reviews/{review_id}/moderate?restaurant_id={w.rid}", headers=header(w.staff), json={"is_published": False})
    body = w.client.get(f"{API}/restaurants/{w.restaurant.slug}/reviews").json()
    assert body["total"] == 0 and body["items"] == []


# ------------------------------------------------------------------ admin moderation & reply

def test_staff_can_list_moderate_and_reply(world):
    w = world
    review_id = w.client.post(f"{API}/reviews", headers=header(w.customer), json={"order_id": w.order.id, "rating": 5}).json()["id"]

    listed = w.client.get(f"{API}/admin/reviews?restaurant_id={w.rid}", headers=header(w.staff)).json()
    assert len(listed) == 1 and listed[0]["reviewer_email"] == w.customer.email

    hidden = w.client.post(f"{API}/admin/reviews/{review_id}/moderate?restaurant_id={w.rid}", headers=header(w.staff), json={"is_published": False})
    assert hidden.status_code == 200 and hidden.json()["is_published"] is False

    replied = w.client.post(f"{API}/admin/reviews/{review_id}/reply?restaurant_id={w.rid}", headers=header(w.staff), json={"reply": "Thank you!"})
    assert replied.status_code == 200 and replied.json()["staff_reply"] == "Thank you!" and replied.json()["staff_reply_at"]


def test_only_staff_can_moderate(world):
    w = world
    review_id = w.client.post(f"{API}/reviews", headers=header(w.customer), json={"order_id": w.order.id, "rating": 5}).json()["id"]
    assert w.client.get(f"{API}/admin/reviews?restaurant_id={w.rid}", headers=header(w.customer)).status_code == 403
    assert w.client.post(
        f"{API}/admin/reviews/{review_id}/moderate?restaurant_id={w.rid}", headers=header(w.customer), json={"is_published": False},
    ).status_code == 403
