"""Customer coupon API routes — check a code before checking out."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.exceptions import AppError, raise_http_for_app_error
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.dependencies.auth import CurrentUser
from app.dependencies.features import requires_feature_for_user
from app.schemas.coupon import CouponPreviewRequest, CouponPreviewResponse
from app.services.coupon_service import CouponService

router = APIRouter(prefix="/coupons")


def get_coupon_service(db: Annotated[Session, Depends(get_db)]) -> CouponService:
    return CouponService(db)


@router.post(
    "/preview",
    response_model=CouponPreviewResponse,
    dependencies=[Depends(requires_feature_for_user("coupons")), rate_limit("coupon_preview", 30, 300)],
)
def preview_coupon(
    data: CouponPreviewRequest,
    user: CurrentUser,
    service: Annotated[CouponService, Depends(get_coupon_service)],
) -> CouponPreviewResponse:
    """Advisory: shows what a code is worth against the cart the customer is looking at. The binding
    discount is worked out again from the server's own subtotal when the order is placed.

    Rate limited so the endpoint can't be used to guess codes at speed.
    """
    try:
        coupon, discount = service.preview(user.restaurant_id, data.code, data.subtotal, user)
    except AppError as exc:
        raise raise_http_for_app_error(exc) from exc
    return CouponPreviewResponse(code=coupon.code, description=coupon.description, discount=discount)
