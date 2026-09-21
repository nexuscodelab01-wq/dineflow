"""Platform-admin (SUPER_ADMIN) routes: things no single restaurant may do for itself."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.exceptions import AppError, NotFoundError, raise_http_for_app_error
from app.db.session import get_db
from app.dependencies.auth import require_roles
from app.models.enums import RoleName
from app.models.restaurant import Restaurant
from app.models.user import User
from app.schemas.features import AuditLogRead, FeatureRead, FeatureSet
from app.services.feature_service import FeatureService

router = APIRouter(prefix="/platform")

PlatformAdmin = Annotated[User, Depends(require_roles(RoleName.SUPER_ADMIN))]


def get_feature_service(db: Annotated[Session, Depends(get_db)]) -> FeatureService:
    return FeatureService(db)


Features = Annotated[FeatureService, Depends(get_feature_service)]


@router.get("/restaurants/{restaurant_id}/features", response_model=list[FeatureRead])
def list_features(restaurant_id: int, _: PlatformAdmin, service: Features) -> list[dict]:
    if service.db.get(Restaurant, restaurant_id) is None:
        raise raise_http_for_app_error(NotFoundError("Restaurant not found"))
    return service.listing(restaurant_id)


@router.put("/restaurants/{restaurant_id}/features/{key}", response_model=list[FeatureRead])
def set_feature(restaurant_id: int, key: str, data: FeatureSet, admin: PlatformAdmin, service: Features) -> list[dict]:
    try:
        return service.set(restaurant_id, key, data.enabled, admin)
    except (AppError, NotFoundError) as exc:
        raise raise_http_for_app_error(exc) from exc


@router.delete("/restaurants/{restaurant_id}/features/{key}", response_model=list[FeatureRead])
def reset_feature(restaurant_id: int, key: str, admin: PlatformAdmin, service: Features) -> list[dict]:
    """Remove the restaurant's override so the flag follows its default again."""
    try:
        return service.set(restaurant_id, key, None, admin)
    except (AppError, NotFoundError) as exc:
        raise raise_http_for_app_error(exc) from exc


@router.get("/audit-log", response_model=list[AuditLogRead])
def audit_log(
    _: PlatformAdmin,
    service: Features,
    restaurant_id: int | None = None,
    limit: int = Query(default=50, ge=1, le=200),
):
    return service.audit_log(restaurant_id, limit)
