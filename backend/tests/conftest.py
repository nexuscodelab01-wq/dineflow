"""Pytest configuration and shared fixtures."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import select

from app.core.security import hash_password
from app.core.config import settings
from app.db.session import SessionLocal, engine, get_db
from app.main import app
from app.models.enums import RoleName
from app.models.role import Role
from app.models.user import User
from app.repositories.user import RoleRepository


def _refuse_to_touch_real_data() -> None:
    """Tests create and delete data. They must only ever run against a scratch database (name ending in _test)."""
    for label, url in (("DATABASE_URL", settings.DATABASE_URL), ("APP_DATABASE_URL", settings.runtime_database_url)):
        name = make_url(url).database or ""
        if not name.endswith("_test"):
            pytest.exit(
                f"Refusing to run: {label} points at database '{name}', not a scratch '*_test' database.\n"
                "Run the tests with e.g.  -e DATABASE_URL=...@postgres:5432/dineflow_test -e APP_DATABASE_URL=  "
                "(or an APP_DATABASE_URL on the same _test database).",
                returncode=2,
            )


_refuse_to_touch_real_data()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def db() -> Session:
    connection = engine.connect()
    transaction = connection.begin()
    # autoflush=False mirrors production SessionLocal so tests catch missing flushes
    session = Session(bind=connection, join_transaction_mode="create_savepoint", autoflush=False)

    RoleRepository(session).ensure_defaults()
    session.flush()

    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


def override_get_db(db: Session):
    """Serve the test's own session for a request. Production gives every request a fresh session; this one is shared,
    so the row-level-security mode a request switched on is switched off again before and after it."""
    from app.db.session import enter_bypass_mode

    def _override():
        enter_bypass_mode(db)
        try:
            yield db
        finally:
            enter_bypass_mode(db)

    return _override


@pytest.fixture
def customer_user(db: Session) -> User:
    role = db.query(Role).filter(Role.name == RoleName.CUSTOMER.value).one()
    user = User(
        email="pytest-customer@demo.com",
        hashed_password=hash_password("Test1234!"),
        first_name="Test",
        last_name="Customer",
        role_id=role.id,
    )
    db.add(user)
    db.flush()
    return db.scalar(select(User).options(joinedload(User.role)).where(User.id == user.id))


@pytest.fixture
def admin_user(db: Session) -> User:
    role = db.query(Role).filter(Role.name == RoleName.RESTAURANT_ADMIN.value).one()
    user = User(
        email="pytest-admin@demo.com",
        hashed_password=hash_password("Test1234!"),
        first_name="Test",
        last_name="Admin",
        role_id=role.id,
    )
    db.add(user)
    db.flush()
    return db.scalar(select(User).options(joinedload(User.role)).where(User.id == user.id))


@pytest.fixture(autouse=True)
def _rate_limiting_off_by_default(monkeypatch):
    """Most tests hammer the same endpoints from one 'client'; rate limiting has its own tests."""
    from app.core.config import settings
    from app.core.rate_limit import limiter

    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)
    limiter.reset()
    yield
    limiter.reset()
