"""Platform-admin (SUPER_ADMIN) routes: things no single restaurant may do for itself."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.core.exceptions import AppError, NotFoundError, raise_http_for_app_error
from app.core.tenancy import site_url
from app.db.session import get_db
from app.dependencies.auth import require_roles
from app.models.audit_log import AuditLog
from app.models.enums import RoleName
from app.models.restaurant import Restaurant
from app.models.user import User
from app.schemas.features import AuditLogRead, FeatureRead, FeatureSet
from app.schemas.restaurant import RestaurantRead, TenantCreateResponse
from app.services.feature_service import FeatureService
from app.services.tenant_provisioning import TEMPLATES, provision_tenant

router = APIRouter(prefix="/platform")

PlatformAdmin = Annotated[User, Depends(require_roles(RoleName.SUPER_ADMIN))]


def get_feature_service(db: Annotated[Session, Depends(get_db)]) -> FeatureService:
    return FeatureService(db)


Features = Annotated[FeatureService, Depends(get_feature_service)]


@router.post("/restaurants", response_model=TenantCreateResponse, status_code=201)
async def create_restaurant(
    admin: PlatformAdmin,
    db: Annotated[Session, Depends(get_db)],
    name: Annotated[str, Form()],
    slug: Annotated[str, Form()],
    owner_email: Annotated[str, Form()],
    owner_name: Annotated[str, Form()] = "Owner",
    color: Annotated[str | None, Form()] = None,
    secondary_color: Annotated[str | None, Form()] = None,
    template: Annotated[str, Form()] = "generic",
    timezone: Annotated[str, Form()] = "UTC",
    custom_domain: Annotated[str | None, Form()] = None,
    branding: Annotated[bool, Form()] = True,
    send_invite: Annotated[bool, Form()] = False,
    logo: Annotated[UploadFile | None, File()] = None,
) -> TenantCreateResponse:
    """Create a restaurant from the platform console — the same thing `python -m app.cli create-tenant` does."""
    logo_bytes = await logo.read() if logo is not None and logo.filename else None
    try:
        result = await run_in_threadpool(
            provision_tenant, db, name=name, slug=slug, owner_email=owner_email, owner_name=owner_name,
            color=color or None, secondary_color=secondary_color or None, logo=logo_bytes, template=template, timezone=timezone,
            custom_domain=custom_domain or None, branding=branding, send_invite=send_invite,
        )
    except (AppError, NotFoundError) as exc:
        raise raise_http_for_app_error(exc) from exc
    restaurant = db.get(Restaurant, result.restaurant_id)
    return TenantCreateResponse(
        restaurant_id=result.restaurant_id, name=result.name, slug=result.slug, order_prefix=result.order_prefix,
        owner_email=result.owner_email, site_url=site_url(restaurant), invite_link=result.invite_link,
    )


@router.get("/restaurants/templates")
def list_templates(_: PlatformAdmin) -> list[str]:
    return sorted(TEMPLATES)


@router.post("/restaurants/{restaurant_id}/verify-domain", response_model=RestaurantRead)
def verify_domain(restaurant_id: int, admin: PlatformAdmin, db: Annotated[Session, Depends(get_db)]) -> RestaurantRead:
    """Mark the restaurant's custom domain as verified.

    A stand-in for real DNS/TLS automation (ROADMAP, Stage E): there is no actual DNS lookup here yet, so
    this only records that a platform admin has checked it by hand. Replace with a real check before
    depending on it for anything security-sensitive.
    """
    restaurant = db.get(Restaurant, restaurant_id)
    if restaurant is None:
        raise raise_http_for_app_error(NotFoundError("Restaurant not found"))
    if not restaurant.custom_domain:
        raise raise_http_for_app_error(AppError("This restaurant has no custom domain set"))
    restaurant.domain_verified_at = datetime.now(UTC)
    db.add(AuditLog(
        restaurant_id=restaurant.id, actor_user_id=admin.id, actor_label=admin.email,
        action="domain.verified", target=restaurant.custom_domain, details={"mock": True},
    ))
    db.commit()
    return RestaurantRead.model_validate(restaurant)


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
