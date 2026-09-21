"""Reservation API tests."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password
from app.db.session import get_db
from app.main import app
from app.models.enums import RoleName, TableStatus
from app.models.restaurant import Restaurant
from app.models.restaurant_table import RestaurantTable
from app.models.role import Role
from app.models.user import User
from tests.conftest import override_get_db


def auth_header(user: User) -> dict[str, str]:
    role_name = user.role.name.value if hasattr(user.role.name, "value") else str(user.role.name)
    token = create_access_token(str(user.id), claims={"role": role_name, "tenant": user.restaurant_id})
    return {"Authorization": f"Bearer {token}"}


def test_availability_and_book_reservation(client: TestClient, db: Session) -> None:
    app.dependency_overrides[get_db] = override_get_db(db)

    customer_role = db.query(Role).filter(Role.name == RoleName.CUSTOMER.value).one()
    customer = User(
        email="reserve-customer@demo.com",
        hashed_password=hash_password("Test1234!"),
        first_name="Reserve",
        last_name="Guest",
        role_id=customer_role.id,
    )
    restaurant = Restaurant(
        name="Reserve Test Kitchen",
        slug="reserve-test-kitchen",
        tax_rate=Decimal("0.10"),
        delivery_fee=Decimal("3.00"),
        dine_in_enabled=True,
    )
    db.add_all([customer, restaurant])
    db.flush()
    customer.restaurant_id = restaurant.id
    db.flush()
    table = RestaurantTable(
        restaurant_id=restaurant.id,
        table_number="R1",
        capacity=4,
        status=TableStatus.AVAILABLE,
    )
    db.add(table)
    db.flush()

    starts = (datetime.now(timezone.utc) + timedelta(hours=2)).replace(microsecond=0)
    availability = client.get(
        f"/api/v1/restaurants/{restaurant.slug}/reservations/availability",
        params={"starts_at": starts.isoformat(), "party_size": 2},
    )
    assert availability.status_code == 200
    assert any(t["id"] == table.id for t in availability.json()["tables"])

    headers = auth_header(customer)
    created = client.post(
        f"/api/v1/restaurants/{restaurant.slug}/reservations",
        headers=headers,
        json={
            "table_id": table.id,
            "party_size": 2,
            "starts_at": starts.isoformat(),
            "duration_minutes": 90,
            "guest_name": "Reserve Guest",
            "guest_email": "reserve-customer@demo.com",
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["status"] == "CONFIRMED"
    assert body["table_id"] == table.id

    # Second overlapping booking should fail
    conflict = client.post(
        f"/api/v1/restaurants/{restaurant.slug}/reservations",
        headers=headers,
        json={
            "table_id": table.id,
            "party_size": 2,
            "starts_at": starts.isoformat(),
            "duration_minutes": 90,
            "guest_name": "Someone Else",
        },
    )
    assert conflict.status_code == 400

    mine = client.get("/api/v1/reservations/me", headers=headers)
    assert mine.status_code == 200
    assert any(r["id"] == body["id"] for r in mine.json())

    app.dependency_overrides.clear()


def test_hold_expires(client: TestClient, db: Session) -> None:
    app.dependency_overrides[get_db] = override_get_db(db)

    customer_role = db.query(Role).filter(Role.name == RoleName.CUSTOMER.value).one()
    customer = User(
        email="hold-customer@demo.com",
        hashed_password=hash_password("Test1234!"),
        first_name="Hold",
        last_name="Guest",
        role_id=customer_role.id,
    )
    restaurant = Restaurant(
        name="Hold Test Kitchen",
        slug="hold-test-kitchen",
        tax_rate=Decimal("0.10"),
        delivery_fee=Decimal("3.00"),
        dine_in_enabled=True,
    )
    db.add_all([customer, restaurant])
    db.flush()
    customer.restaurant_id = restaurant.id
    db.flush()
    table = RestaurantTable(
        restaurant_id=restaurant.id,
        table_number="H1",
        capacity=2,
        status=TableStatus.AVAILABLE,
    )
    db.add(table)
    db.flush()

    starts = (datetime.now(timezone.utc) + timedelta(hours=4)).replace(microsecond=0)
    headers = auth_header(customer)
    created = client.post(
        f"/api/v1/restaurants/{restaurant.slug}/reservations",
        headers=headers,
        json={
            "table_id": table.id,
            "party_size": 2,
            "starts_at": starts.isoformat(),
            "guest_name": "Hold Guest",
            "hold": True,
        },
    )
    assert created.status_code == 201
    assert created.json()["status"] == "HELD"
    assert created.json()["hold_expires_at"] is not None

    app.dependency_overrides.clear()
