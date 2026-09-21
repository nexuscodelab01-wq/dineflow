"""Security hardening: pricing, rate limits, passwords, headers, error handling, config guard."""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import rate_limit as rl
from app.core.config import Settings, settings
from app.db.session import get_db
from app.main import app
from app.models.order import Order
from tests.conftest import override_get_db
from tests.test_menu_orders import _seed_menu


def _login(client: TestClient, user) -> dict[str, str]:
    token = client.post("/api/v1/auth/login", json={"email": user.email, "password": "Test1234!", "restaurant_id": user.restaurant_id}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _order(client, headers, restaurant, item, **extra):
    return client.post(
        "/api/v1/orders", headers=headers,
        json={
            "restaurant_id": restaurant.id, "order_type": "PICKUP",
            "items": [{"menu_item_id": item.id, "quantity": 2, "modifier_option_ids": []}],
            "customer_name": "Test Tester", "customer_email": "menu-test@demo.com", **extra,
        },
    )


# ------------------------------------------------------------------ pricing is server-side only

def test_client_cannot_set_discount_or_table(client: TestClient, db: Session) -> None:
    app.dependency_overrides[get_db] = override_get_db(db)
    restaurant, item, user = _seed_menu(db)
    headers = _login(client, user)

    honest = _order(client, headers, restaurant, item).json()
    cheat = _order(client, headers, restaurant, item, discount="9999.00", table_id=12345).json()

    assert Decimal(cheat["discount"]) == 0
    assert cheat["total"] == honest["total"] and cheat["tax"] == honest["tax"]
    stored = db.scalar(select(Order).where(Order.id == cheat["id"]))
    assert stored.table_id is None          # a pickup order never gets a table from the request
    app.dependency_overrides.clear()


# ------------------------------------------------------------------ rate limiting

@pytest.fixture
def limits_on(monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    rl.limiter.reset()
    yield
    rl.limiter.reset()


def test_login_is_rate_limited_per_account(client: TestClient, db: Session, limits_on) -> None:
    app.dependency_overrides[get_db] = override_get_db(db)
    body = {"email": "victim@demo.com", "password": "wrong-password-1"}
    codes = [client.post("/api/v1/auth/login", json=body).status_code for _ in range(9)]
    assert codes[:8] == [401] * 8
    assert codes[8] == 429

    blocked = client.post("/api/v1/auth/login", json=body)
    assert blocked.status_code == 429 and int(blocked.headers["Retry-After"]) > 0
    assert "Too many requests" in blocked.json()["detail"]

    # A different account from the same place is not locked out by the first one's attempts.
    other = client.post("/api/v1/auth/login", json={"email": "someone-else@demo.com", "password": "wrong-password-1"})
    assert other.status_code == 401
    app.dependency_overrides.clear()


def test_login_is_rate_limited_per_ip(client: TestClient, db: Session, limits_on) -> None:
    app.dependency_overrides[get_db] = override_get_db(db)
    codes = [
        client.post("/api/v1/auth/login", json={"email": f"user{i}@demo.com", "password": "wrong-password-1"}).status_code
        for i in range(22)
    ]
    assert codes[:20] == [401] * 20 and codes[20:] == [429, 429]
    app.dependency_overrides.clear()


def test_registration_is_rate_limited(client: TestClient, db: Session, limits_on) -> None:
    app.dependency_overrides[get_db] = override_get_db(db)
    restaurant = _seed_menu(db)[0]
    codes = []
    for i in range(12):
        r = client.post("/api/v1/auth/register", json={
            "restaurant_id": restaurant.id, "email": f"bulk{i}@demo.com", "password": "Sturdy-Pass9", "first_name": "B", "last_name": "K",
        })
        codes.append(r.status_code)
    assert codes[:10] == [201] * 10 and codes[10:] == [429, 429]
    app.dependency_overrides.clear()


def test_limiter_window_slides(monkeypatch) -> None:
    limiter = rl.RateLimiter()
    clock = {"t": 1000.0}
    monkeypatch.setattr(rl.time, "monotonic", lambda: clock["t"])
    assert [limiter.hit("k", 2, 60) for _ in range(2)] == [None, None]
    retry_after = limiter.hit("k", 2, 60)
    assert retry_after is not None and 1 <= retry_after <= 61
    clock["t"] += 61
    assert limiter.hit("k", 2, 60) is None       # old hits aged out
    assert limiter.hit("other", 2, 60) is None    # keys are independent


def test_forwarded_ip_is_only_trusted_when_configured(client: TestClient, monkeypatch) -> None:
    from starlette.requests import Request

    scope = {"type": "http", "headers": [(b"x-forwarded-for", b"203.0.113.9, 10.0.0.1")], "client": ("10.0.0.1", 1)}
    request = Request(scope)
    monkeypatch.setattr(settings, "TRUST_PROXY_HEADERS", False)
    assert rl.client_ip(request) == "10.0.0.1"
    monkeypatch.setattr(settings, "TRUST_PROXY_HEADERS", True)
    assert rl.client_ip(request) == "203.0.113.9"


# ------------------------------------------------------------------ password rules

@pytest.mark.parametrize("password,expected", [
    ("onlyletters", "letter and one number"),
    ("12345678", "letter and one number"),
    ("Password123", "too common"),
    ("password1", "too common"),
    ("alexander-Pass1", "email name"),   # contains the email's local part
])
def test_weak_passwords_are_rejected(client: TestClient, password: str, expected: str) -> None:
    r = client.post("/api/v1/auth/register", json={
        "restaurant_id": 1, "email": "alexander@demo.com", "password": password, "first_name": "A", "last_name": "B",
    })
    assert r.status_code == 422, r.text
    assert expected in r.json()["errors"][0]["message"], r.json()


def test_strong_password_is_accepted(client: TestClient, db: Session) -> None:
    app.dependency_overrides[get_db] = override_get_db(db)
    r = client.post("/api/v1/auth/register", json={
        "restaurant_id": _seed_menu(db)[0].id, "email": "fresh@demo.com", "password": "Horse-Battery-9", "first_name": "F", "last_name": "R",
    })
    assert r.status_code == 201
    app.dependency_overrides.clear()


# ------------------------------------------------------------------ headers, request ids, errors

def test_security_headers_and_request_id(client: TestClient) -> None:
    r = client.get("/api/v1/health")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "camera=()" in r.headers["Permissions-Policy"]
    assert "Strict-Transport-Security" not in r.headers     # only in production
    assert len(r.headers["X-Request-ID"]) >= 8


def test_request_id_is_echoed_when_valid_and_replaced_when_not(client: TestClient) -> None:
    ok = client.get("/api/v1/health", headers={"X-Request-ID": "trace-abc-12345"})
    assert ok.headers["X-Request-ID"] == "trace-abc-12345"
    bad = client.get("/api/v1/health", headers={"X-Request-ID": "x y\nz<script>"})
    assert bad.headers["X-Request-ID"] != "x y\nz<script>" and " " not in bad.headers["X-Request-ID"]


def test_hsts_only_in_production(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    assert "max-age" in client.get("/api/v1/health").headers["Strict-Transport-Security"]


def test_readiness_reports_database_state(client: TestClient, db: Session) -> None:
    app.dependency_overrides[get_db] = override_get_db(db)
    assert client.get("/api/v1/health/ready").json() == {"status": "ready", "database": "ok"}

    class DeadSession:
        def execute(self, *_args, **_kwargs):
            raise RuntimeError("connection refused")

    def dead_db():
        yield DeadSession()

    app.dependency_overrides[get_db] = dead_db
    r = client.get("/api/v1/health/ready")
    assert r.status_code == 503 and r.json()["detail"] == "Database unavailable"
    assert "connection refused" not in r.text
    app.dependency_overrides.clear()


def test_unhandled_errors_do_not_leak_internals(db: Session) -> None:
    def broken():
        raise RuntimeError("secret database password in this message")
        yield  # pragma: no cover

    app.dependency_overrides[get_db] = broken
    quiet = TestClient(app, raise_server_exceptions=False)
    r = quiet.get("/api/v1/categories", params={"restaurant_id": 1})
    assert r.status_code == 500
    body = r.json()
    assert "secret" not in r.text and body["detail"] == "Something went wrong on our side."
    assert body["request_id"] == r.headers["X-Request-ID"]
    app.dependency_overrides.clear()


# ------------------------------------------------------------------ production config guard

GOOD = dict(
    ENVIRONMENT="production",
    JWT_SECRET="a" * 40,
    JWT_REFRESH_SECRET="b" * 40,
    DATABASE_URL="postgresql+psycopg://app:s3cret-prod@db:5432/app",
    APP_DATABASE_URL="postgresql+psycopg://app_restricted:s3cret-prod-2@db:5432/app",   # not the environment's
)


def test_production_refuses_placeholder_secrets() -> None:
    with pytest.raises(RuntimeError) as exc:
        Settings(**{**GOOD, "JWT_SECRET": "change-me-access-secret-min-32-chars-long"}).assert_production_ready()
    assert "JWT_SECRET" in str(exc.value)
    with pytest.raises(RuntimeError, match="must differ"):
        Settings(**{**GOOD, "JWT_REFRESH_SECRET": GOOD["JWT_SECRET"]}).assert_production_ready()
    with pytest.raises(RuntimeError, match="development database password"):
        Settings(**{**GOOD, "DATABASE_URL": "postgresql+psycopg://dineflow:dineflow_dev_password@db/x"}).assert_production_ready()


def test_production_refuses_the_development_password_for_the_restricted_role() -> None:
    with pytest.raises(RuntimeError) as exc:
        Settings(**{**GOOD, "APP_DATABASE_URL": "postgresql+psycopg://dineflow_app:dineflow_app_dev_password@db/x"}).assert_production_ready()
    assert "restricted role" in str(exc.value)


def test_row_level_security_is_reported_as_enforced_only_with_a_different_restricted_role() -> None:
    assert Settings(**GOOD).rls_enforced is True
    assert Settings(**{**GOOD, "APP_DATABASE_URL": ""}).rls_enforced is False
    assert Settings(**{**GOOD, "APP_DATABASE_URL": GOOD["DATABASE_URL"]}).rls_enforced is False     # same role: nothing restricted


def test_production_accepts_real_config_and_development_is_unrestricted() -> None:
    Settings(**GOOD).assert_production_ready()
    Settings(ENVIRONMENT="development").assert_production_ready()   # placeholders are fine locally
