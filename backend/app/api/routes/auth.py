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
    MessageResponse,
    TokenRefresh,
    TokenResponse,
    UserLogin,
    UserRead,
    UserRegister,
)
from app.services.auth_service import AuthService

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
