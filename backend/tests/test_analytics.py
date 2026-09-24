"""Analytics API tests."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password
from app.db.session import get_db
from app.main import app
from app.models.category import Category
from app.models.enums import OrderStatus, OrderType, PaymentMethod, PaymentStatus, ReservationStatus, RoleName, TableStatus
from app.models.menu_item import MenuItem
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.payment import Payment
from app.models.reservation import Reservation
from app.models.restaurant import Restaurant
from app.models.restaurant_table import RestaurantTable
from app.models.restaurant_user import RestaurantUser
from app.models.role import Role
from app.models.user import User
from tests.conftest import override_get_db
from tests.tenants import header, make_user


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
    assert len(data["sales_by_hour"]) == 24  # every hour present, zero-filled where there's no data
    assert data["no_show"] == {"total_reservations": 0, "no_shows": 0, "rate": 0.0}

    app.dependency_overrides.clear()


@pytest.fixture
def analytics_world(client, db):
    app.dependency_overrides[get_db] = override_get_db(db)
    restaurant = Restaurant(name="Analytics 2 Kitchen", slug="analytics-2-kitchen", tax_rate=Decimal("0.1"))
    db.add(restaurant)
    db.flush()
    admin = make_user(db, "analytics2-admin@iso-demo.com", RoleName.RESTAURANT_ADMIN)
    db.add(RestaurantUser(restaurant_id=restaurant.id, user_id=admin.id))
    table = RestaurantTable(restaurant_id=restaurant.id, table_number="A1", capacity=4, status=TableStatus.AVAILABLE)
    db.add(table)
    db.flush()
    db.expire_all()
    yield type("W", (), {"client": client, "db": db, "rid": restaurant.id, "restaurant": restaurant, "admin": db.get(User, admin.id), "table": table})
    app.dependency_overrides.clear()


def test_no_show_rate_counts_only_expired_bookings_and_excludes_abandoned_holds(analytics_world):
    w = analytics_world
    now = datetime.now(UTC)

    def booking(status, offset_minutes=0):
        start = now + timedelta(minutes=offset_minutes)
        w.db.add(Reservation(
            restaurant_id=w.rid, table_id=w.table.id, party_size=2, guest_name="Guest",
            starts_at=start, ends_at=start + timedelta(minutes=90), status=status,
        ))

    booking(ReservationStatus.COMPLETED)
    booking(ReservationStatus.EXPIRED, 5)
    booking(ReservationStatus.EXPIRED, 10)
    booking(ReservationStatus.CANCELLED, 15)
    booking(ReservationStatus.HELD, 20)  # an abandoned hold was never a real booking — excluded
    w.db.commit()

    r = w.client.get(f"/api/v1/admin/analytics?restaurant_id={w.rid}&range=last_30_days", headers=header(w.admin))
    assert r.status_code == 200, r.text
    no_show = r.json()["no_show"]
    assert no_show == {"total_reservations": 4, "no_shows": 2, "rate": 50.0}


def test_sales_by_hour_buckets_orders_by_their_created_hour(analytics_world):
    w = analytics_world
    category = Category(restaurant_id=w.rid, name="Mains", slug="mains")
    w.db.add(category)
    w.db.flush()
    item = MenuItem(restaurant_id=w.rid, category_id=category.id, name="Burger", price=Decimal("10.00"))
    w.db.add(item)
    w.db.flush()

    noon = datetime.now(UTC).replace(hour=12, minute=0, second=0, microsecond=0)
    order = Order(
        restaurant_id=w.rid, user_id=w.admin.id, order_number="A2-1", order_type=OrderType.PICKUP,
        status=OrderStatus.COMPLETED, subtotal=Decimal("10.00"), tax=Decimal("1.00"), total=Decimal("11.00"),
        customer_name="Guest", customer_email=w.admin.email, created_at=noon, updated_at=noon,
    )
    w.db.add(order)
    w.db.commit()

    r = w.client.get(f"/api/v1/admin/analytics?restaurant_id={w.rid}&range=last_7_days", headers=header(w.admin))
    assert r.status_code == 200, r.text
    by_hour = {row["hour"]: row for row in r.json()["sales_by_hour"]}
    assert by_hour[12]["orders"] == 1
    assert Decimal(by_hour[12]["revenue"]) == Decimal("11.00")
    assert by_hour[11]["orders"] == 0


def test_export_csv_lists_orders_in_range(analytics_world):
    w = analytics_world
    order = Order(
        restaurant_id=w.rid, user_id=w.admin.id, order_number="A2-EXPORT", order_type=OrderType.PICKUP,
        status=OrderStatus.COMPLETED, subtotal=Decimal("20.00"), tax=Decimal("2.00"), total=Decimal("22.00"),
        customer_name="Export Guest", customer_email="export@example.com",
    )
    w.db.add(order)
    w.db.commit()

    r = w.client.get(f"/api/v1/admin/analytics/export.csv?restaurant_id={w.rid}&range=last_7_days", headers=header(w.admin))
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    assert "order_number" in r.text
    assert "A2-EXPORT" in r.text and "export@example.com" in r.text


def test_only_staff_can_export(analytics_world):
    w = analytics_world
    customer = make_user(w.db, "analytics2-cust@iso-demo.com", RoleName.CUSTOMER, restaurant_id=w.rid)
    w.db.commit()
    r = w.client.get(f"/api/v1/admin/analytics/export.csv?restaurant_id={w.rid}&range=last_7_days", headers=header(customer))
    assert r.status_code == 403
