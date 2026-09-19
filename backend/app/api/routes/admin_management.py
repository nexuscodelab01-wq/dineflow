"""Admin API routes."""

from datetime import datetime
from pathlib import Path
from typing import Annotated
import uuid

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.core.exceptions import AppError, NotFoundError, raise_http_for_app_error
from app.db.session import get_db
from app.dependencies.restaurant import AdminUser, RestaurantId, StaffUser
from app.models.enums import OrderStatus, OrderType
from app.models.user import User
from app.schemas.admin import (
    CategoryCreate,
    CategoryReorder,
    CategoryUpdate,
    CustomerSummary,
    DashboardStats,
    KitchenBoard,
    MenuItemCreate,
    MenuItemUpdate,
    MenuModifierCreate,
    MenuModifierUpdate,
    ModifierOptionCreate,
    ModifierOptionUpdate,
    OrderStatusUpdate,
    RestaurantSettingsUpdate,
    TableCreate,
    TableStatusUpdate,
    TableUpdate,
)
from app.schemas.analytics import AnalyticsResponse
from app.schemas.menu import CategoryRead, MenuItemDetailRead, MenuModifierRead
from app.schemas.order import OrderListResponse, OrderRead
from app.schemas.restaurant import RestaurantRead
from app.services.admin_service import AdminService
from app.services.analytics_service import AnalyticsService
from app.utils.date_ranges import DateRangePreset

router = APIRouter(prefix="/admin")

UPLOAD_DIR = Path(__file__).resolve().parents[3] / "uploads" / "menu"
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024


def get_admin_service(db: Annotated[Session, Depends(get_db)]) -> AdminService:
    return AdminService(db)


def get_analytics_service(db: Annotated[Session, Depends(get_db)]) -> AnalyticsService:
    return AnalyticsService(db)


def _handle(exc: Exception):
    if isinstance(exc, (AppError, NotFoundError)):
        raise raise_http_for_app_error(exc) from exc
    raise exc


@router.get("/dashboard", response_model=DashboardStats)
def dashboard(
    _: StaffUser,
    restaurant_id: RestaurantId,
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> DashboardStats:
    return service.dashboard_stats(restaurant_id)


@router.get("/analytics", response_model=AnalyticsResponse)
def analytics(
    _: StaffUser,
    restaurant_id: RestaurantId,
    service: Annotated[AnalyticsService, Depends(get_analytics_service)],
    preset: DateRangePreset = Query(default=DateRangePreset.LAST_7_DAYS, alias="range"),
    start_date: datetime | None = Query(default=None),
    end_date: datetime | None = Query(default=None),
) -> AnalyticsResponse:
    try:
        return service.get_analytics(
            restaurant_id,
            preset,
            start_date=start_date,
            end_date=end_date,
        )
    except AppError as exc:
        raise raise_http_for_app_error(exc) from exc


@router.get("/categories", response_model=list[CategoryRead])
def list_categories(
    _: StaffUser,
    restaurant_id: RestaurantId,
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> list[CategoryRead]:
    return service.list_categories(restaurant_id)


@router.post("/categories", response_model=CategoryRead, status_code=status.HTTP_201_CREATED)
def create_category(
    data: CategoryCreate,
    _: AdminUser,
    restaurant_id: RestaurantId,
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> CategoryRead:
    if data.restaurant_id != restaurant_id:
        raise raise_http_for_app_error(AppError("Restaurant mismatch"))
    try:
        return service.create_category(data)
    except (AppError, NotFoundError) as exc:
        raise raise_http_for_app_error(exc) from exc


@router.put("/categories/{category_id}", response_model=CategoryRead)
def update_category(
    category_id: int,
    data: CategoryUpdate,
    _: AdminUser,
    restaurant_id: RestaurantId,
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> CategoryRead:
    try:
        return service.update_category(category_id, data, restaurant_id)
    except (AppError, NotFoundError) as exc:
        raise raise_http_for_app_error(exc) from exc


@router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(
    category_id: int,
    _: AdminUser,
    restaurant_id: RestaurantId,
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> None:
    try:
        service.delete_category(category_id, restaurant_id)
    except (AppError, NotFoundError) as exc:
        raise raise_http_for_app_error(exc) from exc


@router.patch("/categories/reorder", response_model=list[CategoryRead])
def reorder_categories(
    data: CategoryReorder,
    _: AdminUser,
    restaurant_id: RestaurantId,
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> list[CategoryRead]:
    return service.reorder_categories(data, restaurant_id)


@router.get("/menu", response_model=list[MenuItemDetailRead])
def admin_list_menu(
    _: StaffUser,
    restaurant_id: RestaurantId,
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> list[MenuItemDetailRead]:
    return service.list_menu_items(restaurant_id)


@router.post("/menu", response_model=MenuItemDetailRead, status_code=status.HTTP_201_CREATED)
def create_menu_item(
    data: MenuItemCreate,
    _: AdminUser,
    restaurant_id: RestaurantId,
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> MenuItemDetailRead:
    if data.restaurant_id != restaurant_id:
        raise raise_http_for_app_error(AppError("Restaurant mismatch"))
    try:
        return service.create_menu_item(data)
    except (AppError, NotFoundError) as exc:
        raise raise_http_for_app_error(exc) from exc


@router.put("/menu/{item_id}", response_model=MenuItemDetailRead)
def update_menu_item(
    item_id: int,
    data: MenuItemUpdate,
    _: AdminUser,
    restaurant_id: RestaurantId,
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> MenuItemDetailRead:
    try:
        return service.update_menu_item(item_id, data, restaurant_id)
    except (AppError, NotFoundError) as exc:
        raise raise_http_for_app_error(exc) from exc


@router.delete("/menu/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_menu_item(
    item_id: int,
    _: AdminUser,
    restaurant_id: RestaurantId,
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> None:
    try:
        service.delete_menu_item(item_id, restaurant_id)
    except (AppError, NotFoundError) as exc:
        raise raise_http_for_app_error(exc) from exc


@router.post("/uploads/menu-image")
async def upload_menu_image(
    _: AdminUser,
    restaurant_id: RestaurantId,
    file: UploadFile = File(...),
) -> dict[str, str]:
    content_type = file.content_type or ""
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise raise_http_for_app_error(AppError("Only JPEG, PNG, WebP, or GIF images are allowed"))

    data = await file.read()
    if not data:
        raise raise_http_for_app_error(AppError("Empty file"))
    if len(data) > MAX_IMAGE_BYTES:
        raise raise_http_for_app_error(AppError("Image must be 5MB or smaller"))

    ext = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }[content_type]

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"r{restaurant_id}-{uuid.uuid4().hex}{ext}"
    (UPLOAD_DIR / filename).write_bytes(data)
    return {"url": f"/uploads/menu/{filename}"}


@router.get("/modifiers", response_model=list[MenuModifierRead])
def list_modifiers(
    _: StaffUser,
    restaurant_id: RestaurantId,
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> list[MenuModifierRead]:
    return service.list_modifiers(restaurant_id)


@router.post("/modifiers", response_model=MenuModifierRead, status_code=status.HTTP_201_CREATED)
def create_modifier(
    data: MenuModifierCreate,
    _: AdminUser,
    restaurant_id: RestaurantId,
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> MenuModifierRead:
    if data.restaurant_id != restaurant_id:
        raise raise_http_for_app_error(AppError("Restaurant mismatch"))
    try:
        return service.create_modifier(data)
    except (AppError, NotFoundError) as exc:
        raise raise_http_for_app_error(exc) from exc


@router.put("/modifiers/{modifier_id}", response_model=MenuModifierRead)
def update_modifier(
    modifier_id: int,
    data: MenuModifierUpdate,
    _: AdminUser,
    restaurant_id: RestaurantId,
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> MenuModifierRead:
    try:
        return service.update_modifier(modifier_id, data, restaurant_id)
    except (AppError, NotFoundError) as exc:
        raise raise_http_for_app_error(exc) from exc


@router.delete("/modifiers/{modifier_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_modifier(
    modifier_id: int,
    _: AdminUser,
    restaurant_id: RestaurantId,
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> None:
    try:
        service.delete_modifier(modifier_id, restaurant_id)
    except (AppError, NotFoundError) as exc:
        raise raise_http_for_app_error(exc) from exc


@router.post("/modifiers/{modifier_id}/options", response_model=MenuModifierRead)
def add_modifier_option(
    modifier_id: int,
    data: ModifierOptionCreate,
    _: AdminUser,
    restaurant_id: RestaurantId,
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> MenuModifierRead:
    try:
        return service.add_modifier_option(modifier_id, data, restaurant_id)
    except (AppError, NotFoundError) as exc:
        raise raise_http_for_app_error(exc) from exc


@router.put("/modifier-options/{option_id}", response_model=MenuModifierRead)
def update_modifier_option(
    option_id: int,
    data: ModifierOptionUpdate,
    _: AdminUser,
    restaurant_id: RestaurantId,
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> MenuModifierRead:
    try:
        return service.update_modifier_option(option_id, data, restaurant_id)
    except (AppError, NotFoundError) as exc:
        raise raise_http_for_app_error(exc) from exc


@router.delete("/modifier-options/{option_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_modifier_option(
    option_id: int,
    _: AdminUser,
    restaurant_id: RestaurantId,
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> None:
    try:
        service.delete_modifier_option(option_id, restaurant_id)
    except (AppError, NotFoundError) as exc:
        raise raise_http_for_app_error(exc) from exc


@router.get("/orders", response_model=OrderListResponse)
def admin_list_orders(
    _: StaffUser,
    restaurant_id: RestaurantId,
    service: Annotated[AdminService, Depends(get_admin_service)],
    status_filter: OrderStatus | None = Query(default=None, alias="status"),
    order_type: OrderType | None = None,
    search: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> OrderListResponse:
    return service.list_orders(
        restaurant_id,
        status=status_filter,
        order_type=order_type,
        search=search,
        page=page,
        page_size=page_size,
    )


@router.get("/orders/{order_id}", response_model=OrderRead)
def admin_get_order(
    order_id: int,
    _: StaffUser,
    restaurant_id: RestaurantId,
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> OrderRead:
    try:
        return service.get_order(order_id, restaurant_id)
    except NotFoundError as exc:
        raise raise_http_for_app_error(exc) from exc


@router.patch("/orders/{order_id}/status", response_model=OrderRead)
def update_order_status(
    order_id: int,
    data: OrderStatusUpdate,
    user: StaffUser,
    restaurant_id: RestaurantId,
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> OrderRead:
    try:
        return service.update_order_status(order_id, data, restaurant_id, user)
    except (AppError, NotFoundError) as exc:
        raise raise_http_for_app_error(exc) from exc


@router.get("/kitchen", response_model=KitchenBoard)
def kitchen_board(
    _: StaffUser,
    restaurant_id: RestaurantId,
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> KitchenBoard:
    return service.kitchen_board(restaurant_id)


@router.get("/tables")
def list_tables(
    _: StaffUser,
    restaurant_id: RestaurantId,
    service: Annotated[AdminService, Depends(get_admin_service)],
):
    tables = service.list_tables(restaurant_id)
    return [
        {
            "id": t.id,
            "table_number": t.table_number,
            "capacity": t.capacity,
            "status": t.status.value if hasattr(t.status, "value") else str(t.status),
        }
        for t in tables
    ]


@router.post("/tables", status_code=status.HTTP_201_CREATED)
def create_table(
    data: TableCreate,
    _: AdminUser,
    restaurant_id: RestaurantId,
    service: Annotated[AdminService, Depends(get_admin_service)],
):
    if data.restaurant_id != restaurant_id:
        raise raise_http_for_app_error(AppError("Restaurant mismatch"))
    table = service.create_table(data)
    return {"id": table.id, "table_number": table.table_number, "capacity": table.capacity, "status": table.status.value}


@router.put("/tables/{table_id}")
def update_table(
    table_id: int,
    data: TableUpdate,
    _: AdminUser,
    restaurant_id: RestaurantId,
    service: Annotated[AdminService, Depends(get_admin_service)],
):
    try:
        table = service.update_table(table_id, data, restaurant_id)
        return {"id": table.id, "table_number": table.table_number, "capacity": table.capacity, "status": table.status.value}
    except NotFoundError as exc:
        raise raise_http_for_app_error(exc) from exc


@router.patch("/tables/{table_id}/status")
def update_table_status(
    table_id: int,
    data: TableStatusUpdate,
    _: StaffUser,
    restaurant_id: RestaurantId,
    service: Annotated[AdminService, Depends(get_admin_service)],
):
    try:
        table = service.update_table_status(table_id, data, restaurant_id)
        return {"id": table.id, "status": table.status.value}
    except NotFoundError as exc:
        raise raise_http_for_app_error(exc) from exc


@router.delete("/tables/{table_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_table(
    table_id: int,
    _: AdminUser,
    restaurant_id: RestaurantId,
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> None:
    try:
        service.delete_table(table_id, restaurant_id)
    except NotFoundError as exc:
        raise raise_http_for_app_error(exc) from exc


@router.get("/customers", response_model=list[CustomerSummary])
def list_customers(
    _: StaffUser,
    restaurant_id: RestaurantId,
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> list[CustomerSummary]:
    return service.list_customers(restaurant_id)


@router.get("/customers/{user_id}")
def get_customer(
    user_id: int,
    _: StaffUser,
    restaurant_id: RestaurantId,
    service: Annotated[AdminService, Depends(get_admin_service)],
):
    try:
        return service.get_customer_detail(restaurant_id, user_id)
    except NotFoundError as exc:
        raise raise_http_for_app_error(exc) from exc


@router.get("/settings", response_model=RestaurantRead)
def get_settings(
    _: AdminUser,
    restaurant_id: RestaurantId,
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> RestaurantRead:
    return service.get_settings(restaurant_id)


@router.patch("/settings", response_model=RestaurantRead)
def update_settings(
    data: RestaurantSettingsUpdate,
    _: AdminUser,
    restaurant_id: RestaurantId,
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> RestaurantRead:
    try:
        return service.update_settings(restaurant_id, data)
    except NotFoundError as exc:
        raise raise_http_for_app_error(exc) from exc


@router.get("/ping")
def admin_ping(_: AdminUser) -> dict[str, str]:
    return {"message": "admin ok"}
