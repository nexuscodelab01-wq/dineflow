"""Admin report of POS voids, comps, discounts and refunds — who, how much, why, and who approved it."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.features import requires_feature
from app.dependencies.restaurant import AdminUser, RestaurantId
from app.schemas.pos_control import AdjustmentRead
from app.services.pos_control_service import PosControlService

router = APIRouter(prefix="/admin", dependencies=[Depends(requires_feature("pos_controls"))])


@router.get("/adjustments", response_model=list[AdjustmentRead])
def list_adjustments(
    restaurant_id: RestaurantId, _: AdminUser, db: Annotated[Session, Depends(get_db)],
    start: Annotated[datetime, Query()], end: Annotated[datetime, Query()],
) -> list[AdjustmentRead]:
    return PosControlService(db).list_adjustments(restaurant_id, start, end)
