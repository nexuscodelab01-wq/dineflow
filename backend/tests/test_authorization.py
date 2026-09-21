"""Role-based authorization tests."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.restaurant import Restaurant
from app.models.restaurant_user import RestaurantUser
from app.core.security import create_access_token
from app.db.session import get_db
from app.main import app
from app.models.user import User
from tests.conftest import override_get_db


def auth_header(user: User) -> dict[str, str]:
    role_name = user.role.name.value if hasattr(user.role.name, "value") else str(user.role.name)
    token = create_access_token(str(user.id), claims={"role": role_name, "tenant": user.restaurant_id})
    return {"Authorization": f"Bearer {token}"}


def test_admin_ping_requires_admin_role(
    client: TestClient,
    db: Session,
    customer_user: User,
    admin_user: User,
) -> None:
    app.dependency_overrides[get_db] = override_get_db(db)

    restaurant = Restaurant(name="Ping Kitchen", slug="ping-kitchen")
    db.add(restaurant)
    db.flush()
    db.add(RestaurantUser(restaurant_id=restaurant.id, user_id=admin_user.id))
    db.flush()
    ping = f"/api/v1/admin/ping?restaurant_id={restaurant.id}"

    denied = client.get(ping, headers=auth_header(customer_user))
    assert denied.status_code == 403

    allowed = client.get(ping, headers=auth_header(admin_user))
    assert allowed.status_code == 200
    assert allowed.json()["message"] == "admin ok"

    app.dependency_overrides.clear()


def test_me_requires_authentication(client: TestClient, db: Session) -> None:
    app.dependency_overrides[get_db] = override_get_db(db)

    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401

    app.dependency_overrides.clear()
