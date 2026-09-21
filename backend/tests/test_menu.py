"""Menu API tests."""

from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.main import app
from app.models.category import Category
from app.models.menu_item import MenuItem
from app.models.restaurant import Restaurant
from tests.conftest import override_get_db


def _seed_menu(db: Session) -> tuple[Restaurant, MenuItem]:
    restaurant = Restaurant(
        name="Test Kitchen",
        slug="test-kitchen",
        description="Test",
        tax_rate=Decimal("0.10"),
        delivery_fee=Decimal("5.00"),
    )
    db.add(restaurant)
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
        is_popular=True,
    )
    db.add(item)
    db.flush()
    return restaurant, item


def test_list_categories_and_menu(client: TestClient, db: Session) -> None:
    app.dependency_overrides[get_db] = override_get_db(db)
    restaurant, item = _seed_menu(db)

    categories_response = client.get(f"/api/v1/categories?restaurant_id={restaurant.id}")
    assert categories_response.status_code == 200
    categories = categories_response.json()
    assert len(categories) == 1
    assert categories[0]["name"] == "Mains"

    menu_response = client.get(f"/api/v1/menu?restaurant_id={restaurant.id}")
    assert menu_response.status_code == 200
    menu_data = menu_response.json()
    assert menu_data["total"] >= 1
    assert any(i["name"] == "Test Burger" for i in menu_data["items"])

    detail_response = client.get(f"/api/v1/menu/{item.id}?restaurant_id={restaurant.id}")
    assert detail_response.status_code == 200
    assert detail_response.json()["name"] == "Test Burger"

    app.dependency_overrides.clear()


def test_menu_search_filter(client: TestClient, db: Session) -> None:
    app.dependency_overrides[get_db] = override_get_db(db)
    restaurant, _item = _seed_menu(db)

    search_response = client.get(
        f"/api/v1/menu?restaurant_id={restaurant.id}&search=burger&is_popular=true"
    )
    assert search_response.status_code == 200
    data = search_response.json()
    assert data["total"] >= 1
    assert all("burger" in i["name"].lower() for i in data["items"])

    app.dependency_overrides.clear()


def test_list_restaurants(client: TestClient, db: Session) -> None:
    app.dependency_overrides[get_db] = override_get_db(db)
    restaurant, _item = _seed_menu(db)

    # The directory of all restaurants is platform-only (see test_tenant_isolation); a site's own details stay public.
    assert client.get("/api/v1/restaurants").status_code == 401

    detail_response = client.get(f"/api/v1/restaurants/{restaurant.slug}")
    assert detail_response.status_code == 200
    assert detail_response.json()["name"] == "Test Kitchen"

    app.dependency_overrides.clear()
