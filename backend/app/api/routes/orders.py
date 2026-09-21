"""Customer order API routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.exceptions import AppError, NotFoundError, raise_http_for_app_error
from app.db.session import get_db
from app.core.rate_limit import rate_limit
from app.dependencies.auth import CurrentUser
from app.schemas.order import OrderCreate, OrderListResponse, OrderRead
from app.services.order_service import OrderService

router = APIRouter(prefix="/orders")


def get_order_service(db: Annotated[Session, Depends(get_db)]) -> OrderService:
    return OrderService(db)


@router.post(
    "",
    response_model=OrderRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[rate_limit("order", 30, 600)],
)
def create_order(
    data: OrderCreate,
    user: CurrentUser,
    service: Annotated[OrderService, Depends(get_order_service)],
) -> OrderRead:
    try:
        return service.create_order(data, user)
    except (AppError, NotFoundError) as exc:
        raise raise_http_for_app_error(exc) from exc


@router.get("", response_model=OrderListResponse)
def list_orders(
    user: CurrentUser,
    service: Annotated[OrderService, Depends(get_order_service)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> OrderListResponse:
    return service.list_orders(user, page=page, page_size=page_size)


@router.get("/{order_id}", response_model=OrderRead)
def get_order(
    order_id: int,
    user: CurrentUser,
    service: Annotated[OrderService, Depends(get_order_service)],
) -> OrderRead:
    try:
        return service.get_order(order_id, user)
    except NotFoundError as exc:
        raise raise_http_for_app_error(exc) from exc
