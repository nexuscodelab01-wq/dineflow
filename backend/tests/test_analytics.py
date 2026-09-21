"""Analytics API tests."""

from datetime import UTC, datetime
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password
from app.db.session import get_db
from app.main import app
from app.models.category import Category
from app.models.enums import OrderStatus, OrderType, PaymentMethod, PaymentStatus, RoleName
from app.models.menu_item import MenuItem
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.payment import Payment
from app.models.restaurant import Restaurant
from app.models.restaurant_user import RestaurantUser
from app.models.role import Role
from app.models.user import User
from tests.conftest import override_get_db


def test_analytics_endpoint(client: TestClient, db: Session) -> None:
    app.dependency_overrides[get_db] = override_get_db(db)

    admin_role = db.query(Role).filter(Role.name == RoleName.RESTAURANT_ADMIN.value).one()
    admin = User(
        email="analytics-admin@demo.com",
        hashed_password=hash_password("Test1234!"),
        first_name="Analytics",
        last_name="Admin",
        role_id=admin_role.id,
    )
    restaurant = Restaurant(name="Analytics Kitchen", slug="analytics-kitchen", tax_rate=Decimal("0.10"))
    db.add_all([admin, restaurant])
    db.flush()
    db.add(RestaurantUser(restaurant_id=restaurant.id, user_id=admin.id))

    category = Category(restaurant_id=restaurant.id, name="Pizza", slug="pizza", sort_order=0)
    db.add(category)
    db.flush()
    item = MenuItem(
        restaurant_id=restaurant.id,
        category_id=category.id,
        name="Margherita",
        price=Decimal("15.00"),
    )
    db.add(item)
    db.flush()

    order = Order(
        user_id=admin.id,
        restaurant_id=restaurant.id,
        order_number="AN-001",
        order_type=OrderType.PICKUP,
        status=OrderStatus.COMPLETED,
        subtotal=Decimal("15.00"),
        tax=Decimal("1.50"),
        delivery_fee=Decimal("0.00"),
        discount=Decimal("0.00"),
        total=Decimal("16.50"),
        customer_name="Analytics Admin",
        customer_email=admin.email,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db.add(order)
    db.flush()
    db.add(
        OrderItem(
            order_id=order.id,
            menu_item_id=item.id,
            item_name=item.name,
            quantity=1,
            unit_price=Decimal("15.00"),
            line_total=Decimal("15.00"),
        )
    )
    db.add(
        Payment(
            order_id=order.id,
            amount=Decimal("16.50"),
            status=PaymentStatus.COMPLETED,
            payment_method=PaymentMethod.MOCK,
        )
    )
    db.flush()

    role_name = admin.role.name.value if hasattr(admin.role.name, "value") else str(admin.role.name)
    token = create_access_token(str(admin.id), claims={"role": role_name, "tenant": admin.restaurant_id})
    headers = {"Authorization": f"Bearer {token}"}

    response = client.get(
        f"/api/v1/admin/analytics?restaurant_id={restaurant.id}&range=last_7_days",
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["summary"]["today_orders"] >= 1
    assert len(data["revenue_over_time"]) >= 1
    assert any(c["category_name"] == "Pizza" for c in data["orders_by_category"])

    app.dependency_overrides.clear()
