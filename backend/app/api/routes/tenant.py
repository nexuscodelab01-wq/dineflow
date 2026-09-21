"""Tenant discovery: which restaurant is this site for?"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, raise_http_for_app_error
from app.core.tenancy import resolve_tenant
from app.db.session import get_db
from app.schemas.restaurant import TenantRead
from app.services.feature_service import FeatureService

router = APIRouter()


@router.get("/tenant", response_model=TenantRead)
def current_tenant(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    host: str | None = None,
) -> TenantRead:
    """The restaurant that owns ``host`` (the browser's site address). The frontend calls this once on load;
    it is public because it only returns what the restaurant's own site already shows."""
    restaurant = resolve_tenant(db, host if host is not None else request.headers.get("host"))
    if restaurant is None:
        raise raise_http_for_app_error(NotFoundError("No restaurant lives at this address"))
    tenant = TenantRead.model_validate(restaurant)
    tenant.features = FeatureService(db).resolve(restaurant.id)
    return tenant
