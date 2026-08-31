"""Authentication endpoint tests."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.main import app
from app.models.user import User
from tests.conftest import override_get_db


def test_register_and_login(client: TestClient, db: Session) -> None:
    app.dependency_overrides[get_db] = override_get_db(db)

    register_payload = {
        "email": "newuser@demo.com",
        "password": "SecurePass1!",
        "first_name": "New",
        "last_name": "User",
        "phone": "+14155550000",
    }
    register_response = client.post("/api/v1/auth/register", json=register_payload)
    assert register_response.status_code == 201
    tokens = register_response.json()
    assert tokens["access_token"]
    assert tokens["refresh_token"]
    assert tokens["token_type"] == "bearer"

    me_response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert me_response.status_code == 200
    me = me_response.json()
    assert me["email"] == "newuser@demo.com"
    assert me["role"]["name"] == "CUSTOMER"

    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": "newuser@demo.com", "password": "SecurePass1!"},
    )
    assert login_response.status_code == 200

    app.dependency_overrides.clear()


def test_login_invalid_credentials(client: TestClient, db: Session, customer_user: User) -> None:
    app.dependency_overrides[get_db] = override_get_db(db)

    response = client.post(
        "/api/v1/auth/login",
        json={"email": customer_user.email, "password": "WrongPassword!"},
    )
    assert response.status_code == 401

    app.dependency_overrides.clear()


def test_refresh_token_rotation(client: TestClient, db: Session, customer_user: User) -> None:
    app.dependency_overrides[get_db] = override_get_db(db)

    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": customer_user.email, "password": "Test1234!"},
    )
    tokens = login_response.json()

    refresh_response = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert refresh_response.status_code == 200
    new_tokens = refresh_response.json()
    assert new_tokens["refresh_token"] != tokens["refresh_token"]

    stale_refresh = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert stale_refresh.status_code == 401

    app.dependency_overrides.clear()
