"""Server-side enforcement of feature flags."""

from typing import Annotated, Callable

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.features import FEATURES
from app.db.session import get_db
from app.dependencies.restaurant import RestaurantId
from app.services.feature_service import FeatureService


def requires_feature(key: str) -> Callable[..., None]:
    """Route dependency for staff routes that take `?restaurant_id=`: 403 when the flag is off.

    Runs after the restaurant-access check, so it never reveals a flag to someone who may not see the restaurant.
    """
    if key not in FEATURES:
        raise KeyError(f"Unknown feature flag: {key}")

    def dependency(restaurant_id: RestaurantId, db: Annotated[Session, Depends(get_db)]) -> None:
        FeatureService(db).require(restaurant_id, key)

    return dependency
