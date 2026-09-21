"""Pytest configuration and shared fixtures."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import SessionLocal, engine, get_db
from app.main import app
from app.models.enums import RoleName
from app.models.role import Role
from app.models.user import User
from app.repositories.user import RoleRepository


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
    def _override():
        try:
            yield db
        finally:
            pass

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
