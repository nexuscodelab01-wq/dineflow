"""Customer review API routes — rate and comment on a completed visit."""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.exceptions import AppError, ForbiddenError, NotFoundError, raise_http_for_app_error
from app.db.session import get_db
from app.dependencies.auth import CurrentUser
from app.dependencies.features import requires_feature_for_user
from app.schemas.review import EligibleVisit, ReviewCreate, ReviewRead
from app.services.review_service import ReviewService

router = APIRouter(prefix="/reviews")


def get_review_service(db: Annotated[Session, Depends(get_db)]) -> ReviewService:
    return ReviewService(db)


@router.get("/eligible", response_model=list[EligibleVisit], dependencies=[Depends(requires_feature_for_user("reviews"))])
def list_eligible_visits(
    user: CurrentUser,
    service: Annotated[ReviewService, Depends(get_review_service)],
) -> list[EligibleVisit]:
    return service.eligible_visits(user)


@router.get("", response_model=list[ReviewRead], dependencies=[Depends(requires_feature_for_user("reviews"))])
def list_my_reviews(
    user: CurrentUser,
    service: Annotated[ReviewService, Depends(get_review_service)],
) -> list[ReviewRead]:
    return service.my_reviews(user)


@router.post("", response_model=ReviewRead, status_code=status.HTTP_201_CREATED, dependencies=[Depends(requires_feature_for_user("reviews"))])
def submit_review(
    data: ReviewCreate,
    user: CurrentUser,
    service: Annotated[ReviewService, Depends(get_review_service)],
) -> ReviewRead:
    try:
        return service.submit(user, data)
    except (AppError, ForbiddenError, NotFoundError) as exc:
        raise raise_http_for_app_error(exc) from exc
