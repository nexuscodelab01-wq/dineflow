"""Authentication routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.exceptions import AppError, raise_http_for_app_error
from app.core.rate_limit import client_ip, limiter, rate_limit
from app.db.session import get_db
from app.dependencies.auth import CurrentUser
from app.dependencies.restaurant import list_accessible_restaurants
from app.schemas.restaurant import RestaurantRead
from app.schemas.auth import (
    ChangePassword,
    ForgotPassword,
    ResetPassword,
    MessageResponse,
    TokenRefresh,
    TokenResponse,
    UserLogin,
    UserRead,
    UserRegister,
)
from app.services.auth_service import AuthService
from app.services.password_service import PasswordService

router = APIRouter(prefix="/auth")


def get_auth_service(db: Annotated[Session, Depends(get_db)]) -> AuthService:
    return AuthService(db)


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=201,
    dependencies=[rate_limit("register", 10, 600)],
)
def register(
    data: UserRegister,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> TokenResponse:
    try:
        return service.register(data)
    except AppError as exc:
        raise raise_http_for_app_error(exc) from exc


@router.post("/login", response_model=TokenResponse, dependencies=[rate_limit("login", 20, 60)])
def login(
    data: UserLogin,
    request: Request,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> TokenResponse:
    # Slow down password guessing against one account from one place. Keyed by IP *and* email, so
    # hammering someone's address can't lock the real owner out from their own network.
    limiter.enforce(f"login-account:{client_ip(request)}:{data.email.lower()}", 8, 600)
    try:
        return service.login(data)
    except AppError as exc:
        raise raise_http_for_app_error(exc) from exc


@router.post("/refresh", response_model=TokenResponse, dependencies=[rate_limit("refresh", 60, 60)])
def refresh_token(
    data: TokenRefresh,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> TokenResponse:
    try:
        return service.refresh(data.refresh_token)
    except AppError as exc:
        raise raise_http_for_app_error(exc) from exc


@router.post("/logout", response_model=MessageResponse)
def logout(
    data: TokenRefresh,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> MessageResponse:
    service.logout(data.refresh_token)
    return MessageResponse(message="Logged out")


@router.get("/me", response_model=UserRead)
def me(current_user: CurrentUser) -> UserRead:
    return UserRead.model_validate(current_user)


@router.get("/my-restaurants", response_model=list[RestaurantRead])
def my_restaurants(
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> list[RestaurantRead]:
    """The restaurants this account can manage: all of them for platform admins, memberships for staff,
    nothing for customers."""
    return [RestaurantRead.model_validate(r) for r in list_accessible_restaurants(db, user)]


def get_password_service(db: Annotated[Session, Depends(get_db)]) -> PasswordService:
    return PasswordService(db)


@router.post("/forgot-password", response_model=MessageResponse, dependencies=[rate_limit("forgot", 8, 600)])
def forgot_password(
    data: ForgotPassword,
    request: Request,
    service: Annotated[PasswordService, Depends(get_password_service)],
) -> MessageResponse:
    """Email a reset link if the account exists. The answer is always the same, so this cannot be used to find out
    who has an account."""
    limiter.enforce(f"forgot-account:{data.email.lower()}", 4, 3600)
    service.request_reset(data.email, data.restaurant_id)
    return MessageResponse(message="If that email has an account, we have sent a link to reset the password.")


@router.post("/reset-password", response_model=MessageResponse, dependencies=[rate_limit("reset", 15, 600)])
def reset_password(data: ResetPassword, service: Annotated[PasswordService, Depends(get_password_service)]) -> MessageResponse:
    try:
        service.reset(data.token, data.password)
    except AppError as exc:
        raise raise_http_for_app_error(exc) from exc
    return MessageResponse(message="Your password has been changed. Please sign in.")


@router.post("/change-password", response_model=TokenResponse, dependencies=[rate_limit("change-password", 10, 600)])
def change_password(
    data: ChangePassword,
    user: CurrentUser,
    service: Annotated[PasswordService, Depends(get_password_service)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
) -> TokenResponse:
    """Change the password while signed in. Every other session is signed out; this one continues with fresh tokens."""
    try:
        service.change(user, data.current_password, data.new_password)
    except AppError as exc:
        raise raise_http_for_app_error(exc) from exc
    return auth.issue_tokens(user)
