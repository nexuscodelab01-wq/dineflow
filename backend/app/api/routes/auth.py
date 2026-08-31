"""Authentication routes."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.exceptions import AppError, raise_http_for_app_error
from app.db.session import get_db
from app.dependencies.auth import CurrentUser
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


@router.post("/register", response_model=TokenResponse, status_code=201)
def register(
    data: UserRegister,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> TokenResponse:
    try:
        return service.register(data)
    except AppError as exc:
        raise raise_http_for_app_error(exc) from exc


@router.post("/login", response_model=TokenResponse)
def login(
    data: UserLogin,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> TokenResponse:
    try:
        return service.login(data)
    except AppError as exc:
        raise raise_http_for_app_error(exc) from exc


@router.post("/refresh", response_model=TokenResponse)
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
