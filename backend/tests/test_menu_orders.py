"""Menu and order API tests."""

from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.session import get_db
from app.main import app
from app.models.category import Category
from app.models.enums import RoleName
from app.models.menu_item import MenuItem
from app.models.restaurant import Restaurant
from app.models.role import Role
from app.models.user import User
from tests.conftest import override_get_db


def _seed_menu(db: Session) -> tuple[Restaurant, MenuItem, User]:
    role = db.query(Role).filter(Role.name == RoleName.CUSTOMER.value).one()
    user = User(
        email="menu-test@demo.com",
        hashed_password=hash_password("Test1234!"),
        first_name="Menu",
        last_name="Tester",
        role_id=role.id,
    )
    restaurant = Restaurant(
        name="Test Kitchen",
        slug="test-kitchen",
        description="Test",
        tax_rate=Decimal("0.10"),
        delivery_fee=Decimal("5.00"),
    )
    db.add_all([user, restaurant])
    db.flush()
    user.restaurant_id = restaurant.id
    db.flush()

    category = Category(
        restaurant_id=restaurant.id,
        name="Mains",
        slug="mains",
        sort_order=0,
    )
    db.add(category)
    db.flush()

    item = MenuItem(
        restaurant_id=restaurant.id,
        category_id=category.id,
        name="Test Burger",
        description="Tasty",
        price=Decimal("12.00"),
        is_available=True,
    )
    db.add(item)
    db.flush()
    return restaurant, item, user


def test_list_menu_and_create_order(client: TestClient, db: Session) -> None:
    app.dependency_overrides[get_db] = override_get_db(db)
    restaurant, item, user = _seed_menu(db)

    menu_response = client.get(f"/api/v1/menu?restaurant_id={restaurant.id}")
    assert menu_response.status_code == 200
    menu_data = menu_response.json()
    assert menu_data["total"] >= 1
    assert any(i["name"] == "Test Burger" for i in menu_data["items"])

    detail_response = client.get(f"/api/v1/menu/{item.id}?restaurant_id={restaurant.id}")
    assert detail_response.status_code == 200
    assert detail_response.json()["name"] == "Test Burger"

    login = client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "Test1234!", "restaurant_id": restaurant.id},
    )
    token = login.json()["access_token"]

    order_response = client.post(
        "/api/v1/orders",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "restaurant_id": restaurant.id,
            "order_type": "PICKUP",
            "items": [{"menu_item_id": item.id, "quantity": 2, "modifier_option_ids": []}],
            "customer_name": user.full_name,
            "customer_email": user.email,
        },
    )
    assert order_response.status_code == 201
    order = order_response.json()
    assert order["status"] == "CONFIRMED"
    assert len(order["items"]) == 1
    assert Decimal(order["total"]) > 0

    list_response = client.get(
        "/api/v1/orders",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_response.status_code == 200
    assert list_response.json()["total"] >= 1

    app.dependency_overrides.clear()


def test_unavailable_item_rejected(client: TestClient, db: Session) -> None:
    app.dependency_overrides[get_db] = override_get_db(db)
    restaurant, item, user = _seed_menu(db)
    item.is_available = False
    db.add(item)
    db.flush()

    login = client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "Test1234!", "restaurant_id": restaurant.id},
    )
    token = login.json()["access_token"]

    order_response = client.post(
        "/api/v1/orders",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "restaurant_id": restaurant.id,
            "order_type": "PICKUP",
            "items": [{"menu_item_id": item.id, "quantity": 1, "modifier_option_ids": []}],
            "customer_name": user.full_name,
            "customer_email": user.email,
        },
    )
    assert order_response.status_code == 400

    app.dependency_overrides.clear()
