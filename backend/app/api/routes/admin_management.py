"""Admin API routes."""

from datetime import datetime
from typing import Annotated
import uuid

from fastapi import APIRouter, Depends, File, Header, Query, Response, UploadFile, status
from starlette.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AppError, NotFoundError, raise_http_for_app_error
from app.core.images import THUMB_SIDE, InvalidImage, process_image
from app.core.storage import get_storage, tenant_prefix, thumb_key
from app.db.session import get_db
from app.dependencies.features import requires_feature
from app.dependencies.restaurant import AdminUser, RestaurantId, StaffUser
from app.models.enums import OrderStatus, OrderType, ReservationStatus
from app.schemas.table_session import (
    OpenSessionRead,
    QrTableRead,
    RoundCreate,
    ServiceRequestStaffRead,
    SessionRead,
    SessionRoundRead,
    TransferRequest,
    WaiterTableRead,
)
from app.services.kitchen_service import KitchenService
from app.services.table_session_service import TableSessionService
from app.schemas.admin import (
    CustomerDetail,
    CustomerProfileUpdate,
    CustomerSummary,
    SoldOutUpdate,
    CategoryCreate,
    CategoryReorder,
    CategoryUpdate,
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
    TableLayoutUpdate,
    TableRead,
    TableStatusUpdate,
    TableUpdate,
)
from app.schemas.analytics import AnalyticsResponse
from app.schemas.menu import CategoryRead, MenuItemDetailRead, MenuModifierRead
from app.schemas.order import OrderListResponse, OrderRead
from app.schemas.reservation import (
    AdminAvailabilityResponse,
    AdminReservationCreate,
    ReservationExtend,
    ReservationRead,
    ReservationStatusUpdate,
    ReservationUpdate,
)
from app.schemas.restaurant import RestaurantRead
from app.schemas.coupon import CouponCreate, CouponRead, CouponUpdate
from app.schemas.staff import StaffInvite, StaffInviteRead, StaffRead, StaffUpdate
from app.schemas.loyalty import AdminLoyaltyAccountRead, LoyaltyAdjust
from app.schemas.review import AdminReviewRead, ReviewModerate, ReviewReply
from app.schemas.waitlist import WaitlistCreate, WaitlistRead, WaitlistSeat
from app.services.admin_service import AdminService
from app.services.analytics_service import AnalyticsService
from app.services.reservation_service import ReservationService
from app.services.coupon_service import CouponService
from app.services.staff_service import StaffService
from app.services.loyalty_service import LoyaltyService
from app.services.review_service import ReviewService
from app.services.waitlist_service import WaitlistService
from app.utils.date_ranges import DateRangePreset

router = APIRouter(prefix="/admin")


def get_table_session_service(db: Annotated[Session, Depends(get_db)]) -> TableSessionService:
    return TableSessionService(db)



def get_admin_service(db: Annotated[Session, Depends(get_db)]) -> AdminService:
    return AdminService(db)


def get_analytics_service(db: Annotated[Session, Depends(get_db)]) -> AnalyticsService:
    return AnalyticsService(db)


def get_reservation_service(db: Annotated[Session, Depends(get_db)]) -> ReservationService:
    return ReservationService(db)


def get_waitlist_service(db: Annotated[Session, Depends(get_db)]) -> WaitlistService:
    return WaitlistService(db)


def get_coupon_service(db: Annotated[Session, Depends(get_db)]) -> CouponService:
    return CouponService(db)


def get_staff_service(db: Annotated[Session, Depends(get_db)]) -> StaffService:
    return StaffService(db)


def get_loyalty_service(db: Annotated[Session, Depends(get_db)]) -> LoyaltyService:
    return LoyaltyService(db)


def get_review_service(db: Annotated[Session, Depends(get_db)]) -> ReviewService:
    return ReviewService(db)


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


@router.get("/analytics/export.csv")
def export_analytics_csv(
    _: StaffUser,
    restaurant_id: RestaurantId,
    service: Annotated[AnalyticsService, Depends(get_analytics_service)],
    preset: DateRangePreset = Query(default=DateRangePreset.LAST_7_DAYS, alias="range"),
    start_date: datetime | None = Query(default=None),
    end_date: datetime | None = Query(default=None),
) -> Response:
    try:
        csv_text = service.export_orders_csv(restaurant_id, preset, start_date=start_date, end_date=end_date)
    except AppError as exc:
        raise raise_http_for_app_error(exc) from exc
    return Response(
        content=csv_text, media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="orders-{preset.value}.csv"'},
    )


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


async def _store_image(
    file: UploadFile, restaurant_id: int, kind: str, *, max_side: int, with_thumb: bool
) -> dict[str, str | None]:
    """Validate, optimise and store an uploaded image under this tenant's prefix."""
    limit = settings.MAX_UPLOAD_BYTES
    data = await file.read(limit + 1)  # never pull an unbounded upload into memory
    try:
        image = await run_in_threadpool(
            process_image, data, max_side=max_side, thumb_side=THUMB_SIDE if with_thumb else None, max_bytes=limit
        )
    except InvalidImage as exc:
        raise raise_http_for_app_error(AppError(str(exc))) from exc

    storage = get_storage()
    key = f"{tenant_prefix(restaurant_id, kind)}/{uuid.uuid4().hex}{image.extension}"
    url = await run_in_threadpool(storage.save, key, image.main, image.content_type)
    thumb_url = None
    if image.thumb is not None and (sibling := thumb_key(key)) is not None:
        thumb_url = await run_in_threadpool(storage.save, sibling, image.thumb, image.content_type)
    return {"url": url, "thumb_url": thumb_url}


@router.post("/uploads/menu-image")
async def upload_menu_image(
    _: AdminUser,
    restaurant_id: RestaurantId,
    file: UploadFile = File(...),
) -> dict[str, str | None]:
    """Menu photo: checked by content, scaled, re-encoded as WebP, with a small thumbnail."""
    return await _store_image(file, restaurant_id, "menu", max_side=settings.IMAGE_MAX_SIDE, with_thumb=True)


@router.post("/uploads/logo")
async def upload_logo(
    _: AdminUser,
    restaurant_id: RestaurantId,
    file: UploadFile = File(...),
) -> dict[str, str | None]:
    """Restaurant logo (transparency is kept). Save the returned url via PATCH /admin/settings."""
    return await _store_image(file, restaurant_id, "branding", max_side=800, with_thumb=False)


@router.post("/uploads/gallery-image")
async def upload_gallery_image(
    _: AdminUser,
    restaurant_id: RestaurantId,
    file: UploadFile = File(...),
) -> dict[str, str | None]:
    """A home page gallery photo. Append the returned url to `gallery` via PATCH /admin/settings."""
    return await _store_image(file, restaurant_id, "gallery", max_side=1600, with_thumb=False)


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


def get_kitchen_service(db: Annotated[Session, Depends(get_db)]) -> KitchenService:
    return KitchenService(db)


KitchenActions = Annotated[KitchenService, Depends(get_kitchen_service)]


@router.post("/kitchen/items/{item_id}/bump", status_code=status.HTTP_204_NO_CONTENT)
def bump_item(item_id: int, user: StaffUser, restaurant_id: RestaurantId, service: KitchenActions) -> None:
    """One dish is done. The order turns READY when all its dishes are."""
    try:
        service.bump_item(item_id, restaurant_id, user.id)
    except (AppError, NotFoundError) as exc:
        raise raise_http_for_app_error(exc) from exc


@router.post("/kitchen/items/{item_id}/recall", status_code=status.HTTP_204_NO_CONTENT)
def recall_item(item_id: int, user: StaffUser, restaurant_id: RestaurantId, service: KitchenActions) -> None:
    try:
        service.recall_item(item_id, restaurant_id, user.id)
    except (AppError, NotFoundError) as exc:
        raise raise_http_for_app_error(exc) from exc


@router.post("/kitchen/orders/{order_id}/bump", status_code=status.HTTP_204_NO_CONTENT)
def bump_ticket(order_id: int, user: StaffUser, restaurant_id: RestaurantId, service: KitchenActions, station: str | None = None) -> None:
    """Bump every open dish on a ticket (or only one station's dishes with ?station=BAR)."""
    try:
        service.bump_ticket(order_id, restaurant_id, station, user.id)
    except (AppError, NotFoundError) as exc:
        raise raise_http_for_app_error(exc) from exc


@router.post("/menu/{item_id}/sold-out", response_model=dict)
def set_sold_out(item_id: int, data: SoldOutUpdate, _: StaffUser, restaurant_id: RestaurantId, service: KitchenActions) -> dict:
    """"86" a dish: unavailable everywhere at once (kitchen staff may do this; editing the menu stays admin-only)."""
    try:
        item = service.set_sold_out(item_id, restaurant_id, data.sold_out)
    except (AppError, NotFoundError) as exc:
        raise raise_http_for_app_error(exc) from exc
    return {"id": item.id, "is_available": item.is_available}


@router.get("/kitchen", response_model=KitchenBoard)
def kitchen_board(
    _: StaffUser,
    restaurant_id: RestaurantId,
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> KitchenBoard:
    return service.kitchen_board(restaurant_id)


@router.get("/tables", response_model=list[TableRead])
def list_tables(
    _: StaffUser,
    restaurant_id: RestaurantId,
    service: Annotated[AdminService, Depends(get_admin_service)],
    include_inactive: bool = Query(default=False, description="Also return tables taken out of service"),
) -> list[TableRead]:
    return service.list_tables(restaurant_id, include_inactive=include_inactive)


@router.put("/tables/layout", response_model=list[TableRead])
def update_table_layout(
    data: TableLayoutUpdate,
    _: AdminUser,
    restaurant_id: RestaurantId,
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> list[TableRead]:
    try:
        return service.update_table_layout(restaurant_id, data)
    except AppError as exc:
        raise raise_http_for_app_error(exc) from exc


@router.post("/tables", response_model=TableRead, status_code=status.HTTP_201_CREATED)
def create_table(
    data: TableCreate,
    _: AdminUser,
    restaurant_id: RestaurantId,
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> TableRead:
    if data.restaurant_id != restaurant_id:
        raise raise_http_for_app_error(AppError("Restaurant mismatch"))
    try:
        return service.create_table(data)
    except AppError as exc:
        raise raise_http_for_app_error(exc) from exc


@router.put("/tables/{table_id}", response_model=TableRead)
def update_table(
    table_id: int,
    data: TableUpdate,
    _: AdminUser,
    restaurant_id: RestaurantId,
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> TableRead:
    try:
        return service.update_table(table_id, data, restaurant_id)
    except AppError as exc:
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
        table, cancelled, completed = service.update_table_status(table_id, data, restaurant_id)
    except AppError as exc:
        raise raise_http_for_app_error(exc) from exc
    return {
        "id": table.id,
        "status": table.status.value,
        "cancelled_reservations": cancelled,
        "completed_reservations": completed,
    }


QR_GATE = [Depends(requires_feature("qr_table_ordering"))]


@router.get("/qr/tables", response_model=list[QrTableRead], dependencies=QR_GATE)
def list_qr_tables(_: AdminUser, restaurant_id: RestaurantId, service: Annotated[TableSessionService, Depends(get_table_session_service)]) -> list[QrTableRead]:
    """Every table with its QR token, for printing table tents."""
    return service.qr_tables(restaurant_id)


@router.post("/tables/{table_id}/qr/rotate", response_model=QrTableRead, dependencies=QR_GATE)
def rotate_qr(table_id: int, _: AdminUser, restaurant_id: RestaurantId, service: Annotated[TableSessionService, Depends(get_table_session_service)]) -> QrTableRead:
    """Replace a table's QR code (e.g. it was photographed or the tent was lost). Old links stop working."""
    try:
        return service.rotate_token(table_id, restaurant_id)
    except (AppError, NotFoundError) as exc:
        raise raise_http_for_app_error(exc) from exc


@router.get("/table-sessions", response_model=list[OpenSessionRead], dependencies=QR_GATE)
def list_table_sessions(_: StaffUser, restaurant_id: RestaurantId, service: Annotated[TableSessionService, Depends(get_table_session_service)]) -> list[OpenSessionRead]:
    return service.open_sessions(restaurant_id)


@router.post("/table-sessions/{session_id}/close", status_code=status.HTTP_204_NO_CONTENT, dependencies=QR_GATE)
def close_table_session(session_id: int, user: StaffUser, restaurant_id: RestaurantId, service: Annotated[TableSessionService, Depends(get_table_session_service)]) -> None:
    """End a table's tab: guest passes stop working, the table goes to cleaning and its QR code is replaced."""
    try:
        service.close_session(session_id, restaurant_id, user.id)
    except (AppError, NotFoundError) as exc:
        raise raise_http_for_app_error(exc) from exc


@router.get("/waiter/floor", response_model=list[WaiterTableRead], dependencies=QR_GATE)
def waiter_floor(_: StaffUser, restaurant_id: RestaurantId, service: Annotated[TableSessionService, Depends(get_table_session_service)]) -> list[WaiterTableRead]:
    """Every table with its live tab, waiting requests and finished-but-not-served rounds."""
    return service.waiter_floor(restaurant_id)


@router.get("/table-sessions/{session_id}", response_model=SessionRead, dependencies=QR_GATE)
def table_session_detail(session_id: int, _: StaffUser, restaurant_id: RestaurantId, service: Annotated[TableSessionService, Depends(get_table_session_service)]) -> SessionRead:
    try:
        return service.view(service.staff_session(session_id, restaurant_id))
    except (AppError, NotFoundError) as exc:
        raise raise_http_for_app_error(exc) from exc


@router.post("/table-sessions/{session_id}/orders", response_model=SessionRoundRead, status_code=status.HTTP_201_CREATED, dependencies=QR_GATE)
def staff_send_round(
    session_id: int,
    data: RoundCreate,
    user: StaffUser,
    restaurant_id: RestaurantId,
    service: Annotated[TableSessionService, Depends(get_table_session_service)],
    idempotency_key: Annotated[str | None, Header(max_length=64)] = None,
) -> SessionRoundRead:
    """A waiter sends a round to the kitchen on the table's behalf (a guest without a phone, a walk-in, a correction)."""
    try:
        return service.place_round(None, service.staff_session(session_id, restaurant_id), data, idempotency_key, staff_user=user)
    except (AppError, NotFoundError) as exc:
        raise raise_http_for_app_error(exc) from exc


@router.post("/table-sessions/{session_id}/transfer", status_code=status.HTTP_204_NO_CONTENT, dependencies=QR_GATE)
def transfer_table_session(session_id: int, data: TransferRequest, _: StaffUser, restaurant_id: RestaurantId, service: Annotated[TableSessionService, Depends(get_table_session_service)]) -> None:
    """Move a party's tab to another (free) table."""
    try:
        service.transfer(session_id, restaurant_id, data.table_id)
    except (AppError, NotFoundError) as exc:
        raise raise_http_for_app_error(exc) from exc


@router.get("/service-requests", response_model=list[ServiceRequestStaffRead], dependencies=QR_GATE)
def list_service_requests(_: StaffUser, restaurant_id: RestaurantId, service: Annotated[TableSessionService, Depends(get_table_session_service)]) -> list[ServiceRequestStaffRead]:
    """Tables waiting for a waiter or the bill, oldest first."""
    return service.open_requests(restaurant_id)


@router.post("/service-requests/{request_id}/done", status_code=status.HTTP_204_NO_CONTENT, dependencies=QR_GATE)
def finish_service_request(request_id: int, user: StaffUser, restaurant_id: RestaurantId, service: Annotated[TableSessionService, Depends(get_table_session_service)]) -> None:
    try:
        service.resolve_request(request_id, restaurant_id, user.id)
    except (AppError, NotFoundError) as exc:
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
    except AppError as exc:
        raise raise_http_for_app_error(exc) from exc


@router.get("/reservations/availability", response_model=AdminAvailabilityResponse, dependencies=[Depends(requires_feature("reservations"))])
def admin_reservation_availability(
    _: StaffUser,
    restaurant_id: RestaurantId,
    service: Annotated[ReservationService, Depends(get_reservation_service)],
    starts_at: datetime,
    party_size: int = Query(default=1, ge=1, le=20),
    duration_minutes: int = Query(default=90, ge=30, le=240),
    exclude_reservation_id: int | None = Query(default=None, description="Ignore this booking (when editing it)"),
) -> AdminAvailabilityResponse:
    try:
        return service.get_admin_availability(
            restaurant_id,
            starts_at=starts_at,
            party_size=party_size,
            duration_minutes=duration_minutes,
            exclude_reservation_id=exclude_reservation_id,
        )
    except AppError as exc:
        raise raise_http_for_app_error(exc) from exc


@router.get("/reservations", response_model=list[ReservationRead], dependencies=[Depends(requires_feature("reservations"))])
def list_reservations(
    _: StaffUser,
    restaurant_id: RestaurantId,
    service: Annotated[ReservationService, Depends(get_reservation_service)],
    start: datetime | None = Query(default=None, description="Include bookings starting at/after this instant"),
    end: datetime | None = Query(default=None, description="Include bookings starting before this instant"),
    status_filter: ReservationStatus | None = Query(default=None, alias="status"),
) -> list[ReservationRead]:
    return service.list_restaurant_reservations(restaurant_id, start=start, end=end, status=status_filter)


@router.post("/reservations", response_model=ReservationRead, status_code=status.HTTP_201_CREATED, dependencies=[Depends(requires_feature("reservations"))])
def create_admin_reservation(
    data: AdminReservationCreate,
    _: StaffUser,
    restaurant_id: RestaurantId,
    service: Annotated[ReservationService, Depends(get_reservation_service)],
) -> ReservationRead:
    try:
        return service.create_admin_reservation(restaurant_id, data)
    except AppError as exc:
        raise raise_http_for_app_error(exc) from exc


@router.patch("/reservations/{reservation_id}", response_model=ReservationRead, dependencies=[Depends(requires_feature("reservations"))])
def update_admin_reservation(
    reservation_id: int,
    data: ReservationUpdate,
    _: StaffUser,
    restaurant_id: RestaurantId,
    service: Annotated[ReservationService, Depends(get_reservation_service)],
) -> ReservationRead:
    try:
        return service.update_reservation(reservation_id, restaurant_id, data)
    except AppError as exc:
        raise raise_http_for_app_error(exc) from exc


@router.post("/reservations/{reservation_id}/extend", response_model=ReservationRead, dependencies=[Depends(requires_feature("reservations"))])
def extend_reservation(
    reservation_id: int,
    data: ReservationExtend,
    _: StaffUser,
    restaurant_id: RestaurantId,
    service: Annotated[ReservationService, Depends(get_reservation_service)],
) -> ReservationRead:
    try:
        return service.extend_reservation(reservation_id, restaurant_id, data)
    except AppError as exc:
        raise raise_http_for_app_error(exc) from exc


@router.patch("/reservations/{reservation_id}/status", response_model=ReservationRead, dependencies=[Depends(requires_feature("reservations"))])
def update_reservation_status(
    reservation_id: int,
    data: ReservationStatusUpdate,
    _: StaffUser,
    restaurant_id: RestaurantId,
    service: Annotated[ReservationService, Depends(get_reservation_service)],
) -> ReservationRead:
    try:
        return service.update_status(reservation_id, restaurant_id, data)
    except AppError as exc:
        raise raise_http_for_app_error(exc) from exc


# ------------------------------------------------------------------ waitlist (walk-in queue)

@router.get("/waitlist", response_model=list[WaitlistRead], dependencies=[Depends(requires_feature("reservations"))])
def list_waitlist(
    _: StaffUser,
    restaurant_id: RestaurantId,
    service: Annotated[WaitlistService, Depends(get_waitlist_service)],
) -> list[WaitlistRead]:
    return service.list_active(restaurant_id)


@router.post("/waitlist", response_model=WaitlistRead, status_code=status.HTTP_201_CREATED, dependencies=[Depends(requires_feature("reservations"))])
def add_to_waitlist(
    data: WaitlistCreate,
    _: StaffUser,
    restaurant_id: RestaurantId,
    service: Annotated[WaitlistService, Depends(get_waitlist_service)],
) -> WaitlistRead:
    try:
        return service.add(restaurant_id, data)
    except AppError as exc:
        raise raise_http_for_app_error(exc) from exc


@router.post("/waitlist/{entry_id}/notify", response_model=WaitlistRead, dependencies=[Depends(requires_feature("reservations"))])
def notify_waitlist_entry(
    entry_id: int,
    _: StaffUser,
    restaurant_id: RestaurantId,
    service: Annotated[WaitlistService, Depends(get_waitlist_service)],
) -> WaitlistRead:
    try:
        return service.notify(entry_id, restaurant_id)
    except AppError as exc:
        raise raise_http_for_app_error(exc) from exc


@router.post("/waitlist/{entry_id}/seat", response_model=WaitlistRead, dependencies=[Depends(requires_feature("reservations"))])
def seat_waitlist_entry(
    entry_id: int,
    data: WaitlistSeat,
    _: StaffUser,
    restaurant_id: RestaurantId,
    service: Annotated[WaitlistService, Depends(get_waitlist_service)],
) -> WaitlistRead:
    try:
        return service.seat(entry_id, restaurant_id, data)
    except AppError as exc:
        raise raise_http_for_app_error(exc) from exc


@router.post("/waitlist/{entry_id}/cancel", response_model=WaitlistRead, dependencies=[Depends(requires_feature("reservations"))])
def cancel_waitlist_entry(
    entry_id: int,
    _: StaffUser,
    restaurant_id: RestaurantId,
    service: Annotated[WaitlistService, Depends(get_waitlist_service)],
) -> WaitlistRead:
    try:
        return service.cancel(entry_id, restaurant_id)
    except AppError as exc:
        raise raise_http_for_app_error(exc) from exc


# ------------------------------------------------------------------ reviews

@router.get("/reviews", response_model=list[AdminReviewRead], dependencies=[Depends(requires_feature("reviews"))])
def list_reviews(
    _: StaffUser,
    restaurant_id: RestaurantId,
    service: Annotated[ReviewService, Depends(get_review_service)],
) -> list[AdminReviewRead]:
    return service.admin_list(restaurant_id)


@router.post("/reviews/{review_id}/moderate", response_model=AdminReviewRead, dependencies=[Depends(requires_feature("reviews"))])
def moderate_review(
    review_id: int,
    data: ReviewModerate,
    _: StaffUser,
    restaurant_id: RestaurantId,
    service: Annotated[ReviewService, Depends(get_review_service)],
) -> AdminReviewRead:
    try:
        return service.moderate(review_id, restaurant_id, data.is_published)
    except AppError as exc:
        raise raise_http_for_app_error(exc) from exc


@router.post("/reviews/{review_id}/reply", response_model=AdminReviewRead, dependencies=[Depends(requires_feature("reviews"))])
def reply_to_review(
    review_id: int,
    data: ReviewReply,
    _: StaffUser,
    restaurant_id: RestaurantId,
    service: Annotated[ReviewService, Depends(get_review_service)],
) -> AdminReviewRead:
    try:
        return service.reply(review_id, restaurant_id, data.reply)
    except AppError as exc:
        raise raise_http_for_app_error(exc) from exc


# ------------------------------------------------------------------ staff

@router.get("/staff", response_model=list[StaffRead])
def list_staff(
    _: StaffUser,
    restaurant_id: RestaurantId,
    service: Annotated[StaffService, Depends(get_staff_service)],
) -> list[StaffRead]:
    return service.list_for_restaurant(restaurant_id)


@router.post("/staff", response_model=StaffInviteRead, status_code=status.HTTP_201_CREATED)
def invite_staff(
    data: StaffInvite,
    admin: AdminUser,
    restaurant_id: RestaurantId,
    service: Annotated[StaffService, Depends(get_staff_service)],
) -> StaffInviteRead:
    try:
        return service.invite(restaurant_id, data, admin)
    except AppError as exc:
        raise raise_http_for_app_error(exc) from exc


@router.patch("/staff/{membership_id}", response_model=StaffRead)
def update_staff(
    membership_id: int,
    data: StaffUpdate,
    admin: AdminUser,
    restaurant_id: RestaurantId,
    service: Annotated[StaffService, Depends(get_staff_service)],
) -> StaffRead:
    try:
        return service.update(membership_id, restaurant_id, data, admin)
    except AppError as exc:
        raise raise_http_for_app_error(exc) from exc


@router.post("/staff/{membership_id}/resend-invite")
def resend_staff_invite(
    membership_id: int,
    _: AdminUser,
    restaurant_id: RestaurantId,
    service: Annotated[StaffService, Depends(get_staff_service)],
) -> dict[str, str]:
    try:
        link = service.resend_invite(membership_id, restaurant_id)
    except AppError as exc:
        raise raise_http_for_app_error(exc) from exc
    return {"invite_link": link}


# ------------------------------------------------------------------ coupons

@router.get("/coupons", response_model=list[CouponRead], dependencies=[Depends(requires_feature("coupons"))])
def list_coupons(
    _: StaffUser,
    restaurant_id: RestaurantId,
    service: Annotated[CouponService, Depends(get_coupon_service)],
) -> list[CouponRead]:
    return service.list_for_restaurant(restaurant_id)


@router.post("/coupons", response_model=CouponRead, status_code=status.HTTP_201_CREATED, dependencies=[Depends(requires_feature("coupons"))])
def create_coupon(
    data: CouponCreate,
    _: AdminUser,
    restaurant_id: RestaurantId,
    service: Annotated[CouponService, Depends(get_coupon_service)],
) -> CouponRead:
    try:
        return service.create(restaurant_id, data)
    except AppError as exc:
        raise raise_http_for_app_error(exc) from exc


@router.patch("/coupons/{coupon_id}", response_model=CouponRead, dependencies=[Depends(requires_feature("coupons"))])
def update_coupon(
    coupon_id: int,
    data: CouponUpdate,
    _: AdminUser,
    restaurant_id: RestaurantId,
    service: Annotated[CouponService, Depends(get_coupon_service)],
) -> CouponRead:
    try:
        return service.update(coupon_id, restaurant_id, data)
    except AppError as exc:
        raise raise_http_for_app_error(exc) from exc


@router.delete("/coupons/{coupon_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(requires_feature("coupons"))])
def delete_coupon(
    coupon_id: int,
    _: AdminUser,
    restaurant_id: RestaurantId,
    service: Annotated[CouponService, Depends(get_coupon_service)],
) -> None:
    try:
        service.delete(coupon_id, restaurant_id)
    except AppError as exc:
        raise raise_http_for_app_error(exc) from exc


# ------------------------------------------------------------------ loyalty

@router.get("/loyalty", response_model=list[AdminLoyaltyAccountRead], dependencies=[Depends(requires_feature("loyalty"))])
def list_loyalty_accounts(
    _: StaffUser,
    restaurant_id: RestaurantId,
    service: Annotated[LoyaltyService, Depends(get_loyalty_service)],
) -> list[AdminLoyaltyAccountRead]:
    return service.admin_list(restaurant_id)


@router.post("/loyalty/{user_id}/adjust", response_model=AdminLoyaltyAccountRead, dependencies=[Depends(requires_feature("loyalty"))])
def adjust_loyalty_points(
    user_id: int,
    data: LoyaltyAdjust,
    staff: StaffUser,
    restaurant_id: RestaurantId,
    service: Annotated[LoyaltyService, Depends(get_loyalty_service)],
) -> AdminLoyaltyAccountRead:
    try:
        return service.admin_adjust(restaurant_id, user_id, data.points, data.note, staff)
    except AppError as exc:
        raise raise_http_for_app_error(exc) from exc


@router.get("/customers", response_model=list[CustomerSummary])
def list_customers(
    _: StaffUser,
    restaurant_id: RestaurantId,
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> list[CustomerSummary]:
    return service.list_customers(restaurant_id)


@router.get("/customers/{user_id}", response_model=CustomerDetail)
def get_customer(
    user_id: int,
    _: StaffUser,
    restaurant_id: RestaurantId,
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> CustomerDetail:
    try:
        return service.get_customer_detail(restaurant_id, user_id)
    except NotFoundError as exc:
        raise raise_http_for_app_error(exc) from exc


@router.patch("/customers/{user_id}", response_model=CustomerSummary)
def update_customer(
    user_id: int,
    data: CustomerProfileUpdate,
    _: StaffUser,
    restaurant_id: RestaurantId,
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> CustomerSummary:
    """Notes, allergies and the VIP flag a restaurant keeps on its own guest."""
    try:
        return service.update_customer_profile(restaurant_id, user_id, data)
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
def admin_ping(_: AdminUser, restaurant_id: RestaurantId) -> dict[str, str]:
    return {"message": "admin ok"}
