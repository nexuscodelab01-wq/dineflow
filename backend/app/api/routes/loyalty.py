"""Customer loyalty API routes — view your own points balance and history."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.auth import CurrentUser
from app.dependencies.features import requires_feature_for_user
from app.schemas.loyalty import LoyaltyAccountRead
from app.services.loyalty_service import LoyaltyService

router = APIRouter(prefix="/loyalty")


def get_loyalty_service(db: Annotated[Session, Depends(get_db)]) -> LoyaltyService:
    return LoyaltyService(db)


@router.get("", response_model=LoyaltyAccountRead, dependencies=[Depends(requires_feature_for_user("loyalty"))])
def my_loyalty_account(
    user: CurrentUser,
    service: Annotated[LoyaltyService, Depends(get_loyalty_service)],
) -> LoyaltyAccountRead:
    return service.my_account(user.restaurant_id, user)
