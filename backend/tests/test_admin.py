"""Admin API tests."""

from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password
from app.db.session import get_db
from app.main import app
from app.models.category import Category
from app.models.enums import RoleName
from app.models.menu_item import MenuItem
from app.models.restaurant import Restaurant
from app.models.restaurant_user import RestaurantUser
from app.models.role import Role
from app.models.user import User
from tests.conftest import override_get_db


def auth_header(user: User) -> dict[str, str]:
    role_name = user.role.name.value if hasattr(user.role.name, "value") else str(user.role.name)
    token = create_access_token(str(user.id), claims={"role": role_name})
    return {"Authorization": f"Bearer {token}"}


def test_admin_dashboard_and_menu(client: TestClient, db: Session) -> None:
    app.dependency_overrides[get_db] = override_get_db(db)

    admin_role = db.query(Role).filter(Role.name == RoleName.RESTAURANT_ADMIN.value).one()
    admin = User(
        email="phase7-admin@demo.com",
        hashed_password=hash_password("Test1234!"),
        first_name="Phase",
        last_name="Admin",
        role_id=admin_role.id,
    )
    restaurant = Restaurant(
        name="Phase 7 Kitchen",
        slug="phase-7-kitchen",
        tax_rate=Decimal("0.10"),
        delivery_fee=Decimal("3.00"),
    )
    db.add_all([admin, restaurant])
    db.flush()
    db.add(RestaurantUser(restaurant_id=restaurant.id, user_id=admin.id))
    db.flush()

    category = Category(
        restaurant_id=restaurant.id,
        name="Mains",
        slug="mains",
        sort_order=0,
    )
    db.add(category)
    db.flush()
    db.add(
        MenuItem(
            restaurant_id=restaurant.id,
            category_id=category.id,
            name="Admin Burger",
            description="Staff managed",
            price=Decimal("14.00"),
            is_available=True,
        )
    )
    db.flush()

    headers = auth_header(admin)
    dashboard = client.get(f"/api/v1/admin/dashboard?restaurant_id={restaurant.id}", headers=headers)
    assert dashboard.status_code == 200
    assert "today_orders" in dashboard.json()

    menu = client.get(f"/api/v1/admin/menu?restaurant_id={restaurant.id}", headers=headers)
    assert menu.status_code == 200
    assert any(item["name"] == "Admin Burger" for item in menu.json())

    create = client.post(
        f"/api/v1/admin/menu?restaurant_id={restaurant.id}",
        headers=headers,
        json={
            "restaurant_id": restaurant.id,
            "category_id": category.id,
            "name": "New Pasta",
            "price": "16.50",
            "is_available": True,
        },
    )
    assert create.status_code == 201
    assert create.json()["name"] == "New Pasta"

    orders = client.get(f"/api/v1/admin/orders?restaurant_id={restaurant.id}", headers=headers)
    assert orders.status_code == 200
    assert "items" in orders.json()

    ping = client.get("/api/v1/admin/ping", headers=headers)
    assert ping.status_code == 200

    app.dependency_overrides.clear()
