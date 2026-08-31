"""Authentication business logic."""

import logging

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, UnauthorizedError
from app.core.security import (
    create_access_token,
    create_refresh_token_value,
    hash_password,
    hash_token,
    refresh_token_expires_at,
    verify_password,
)
from app.models.enums import RoleName
from app.models.user import User
from app.repositories.refresh_token import RefreshTokenRepository
from app.repositories.user import RoleRepository, UserRepository
from app.schemas.auth import TokenResponse, UserLogin, UserRegister

logger = logging.getLogger(__name__)


class AuthService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.users = UserRepository(db)
        self.roles = RoleRepository(db)
        self.refresh_tokens = RefreshTokenRepository(db)

    def register(self, data: UserRegister) -> TokenResponse:
        if self.users.get_by_email(data.email):
            raise ConflictError("Email already registered")

        self.roles.ensure_defaults()
        customer_role = self.roles.get_by_name(RoleName.CUSTOMER.value)
        if customer_role is None:
            raise ConflictError("Default customer role is missing")

        user = self.users.create(
            email=data.email,
            hashed_password=hash_password(data.password),
            first_name=data.first_name,
            last_name=data.last_name,
            phone=data.phone,
            role_id=customer_role.id,
        )
        self.db.commit()
        logger.info("User registered: user_id=%s", user.id)
        return self._issue_tokens(user)

    def login(self, data: UserLogin) -> TokenResponse:
        user = self.users.get_by_email(data.email)
        if user is None or not verify_password(data.password, user.hashed_password):
            raise UnauthorizedError("Invalid email or password")
        if not user.is_active:
            raise UnauthorizedError("Account is inactive")

        logger.info("User login: user_id=%s", user.id)
        return self._issue_tokens(user)

    def refresh(self, refresh_token: str) -> TokenResponse:
        token_hash = hash_token(refresh_token)
        record = self.refresh_tokens.get_valid(token_hash)
        if record is None:
            raise UnauthorizedError("Invalid or expired refresh token")

        user = self.users.get_by_id(record.user_id)
        if user is None or not user.is_active:
            raise UnauthorizedError("User not available")

        self.refresh_tokens.revoke(record)
        self.db.commit()
        return self._issue_tokens(user)

    def logout(self, refresh_token: str) -> None:
        token_hash = hash_token(refresh_token)
        record = self.refresh_tokens.get_valid(token_hash)
        if record is not None:
            self.refresh_tokens.revoke(record)
            self.db.commit()
            logger.info("User logout: user_id=%s", record.user_id)

    def _issue_tokens(self, user: User) -> TokenResponse:
        access_token = create_access_token(
            str(user.id),
            claims={
                "role": (
                    user.role.name.value
                    if hasattr(user.role.name, "value")
                    else str(user.role.name)
                )
            },
        )
        refresh_value = create_refresh_token_value()
        self.refresh_tokens.create(
            user_id=user.id,
            token_hash=hash_token(refresh_value),
            expires_at=refresh_token_expires_at(),
        )
        self.db.commit()
        return TokenResponse(access_token=access_token, refresh_token=refresh_value)
