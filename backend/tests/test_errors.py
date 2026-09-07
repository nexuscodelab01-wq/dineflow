"""Consistent API error response tests."""

from fastapi.testclient import TestClient


def test_validation_error_format(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "not-an-email", "password": "short", "first_name": "", "last_name": ""},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["detail"] == "Validation failed"
    assert isinstance(body["errors"], list)
    assert len(body["errors"]) >= 1
    assert "field" in body["errors"][0]
    assert "message" in body["errors"][0]


def test_not_found_error_format(client: TestClient) -> None:
    response = client.get("/api/v1/menu/999999")
    assert response.status_code == 404
    body = response.json()
    assert isinstance(body["detail"], str)
    assert body["detail"]


def test_unauthorized_error_format(client: TestClient) -> None:
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    body = response.json()
    assert isinstance(body["detail"], str)
