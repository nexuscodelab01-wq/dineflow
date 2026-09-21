"""Security helpers: password hashing and JWT tokens."""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def create_access_token(subject: str, claims: dict[str, Any] | None = None) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": subject, "exp": expire, "type": "access"}
    if claims:
        payload.update(claims)
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


GUEST_TOKEN_HOURS = 12


def create_guest_token(guest_id: int, session_id: int, restaurant_id: int) -> str:
    """A device's pass to one open table session. Its `type` differs from an account token, so it can never be
    used as a login: `decode_access_token` refuses it, and this one refuses account tokens."""
    payload = {
        "sub": str(guest_id), "type": "guest", "sess": session_id, "tenant": restaurant_id,
        "exp": datetime.now(UTC) + timedelta(hours=GUEST_TOKEN_HOURS),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_guest_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except JWTError as exc:
        raise ValueError("Invalid guest token") from exc
    if payload.get("type") != "guest":
        raise ValueError("Invalid token type")
    return payload


def create_refresh_token_value() -> str:
    return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except JWTError as exc:
        raise ValueError("Invalid access token") from exc
    if payload.get("type") != "access":
        raise ValueError("Invalid token type")
    return payload


def refresh_token_expires_at() -> datetime:
    return datetime.now(UTC) + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
