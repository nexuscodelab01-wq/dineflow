"""Server-side enforcement of feature flags."""

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.exceptions import ForbiddenError
from app.db.session import get_db
from app.dependencies.auth import CurrentUser
from app.dependencies.pos import CurrentDevice, CurrentPosStaff
from app.dependencies.restaurant import RestaurantId
from app.services.feature_service import FeatureService


def requires_feature(key: str) -> Callable[..., None]:
    """Route dependency for staff routes that take `?restaurant_id=`: 403 when the flag is off.

    Runs after the restaurant-access check, so it never reveals a flag to someone who may not see the restaurant.
    The catalog is database-backed now (FeatureService), so there's nothing to validate `key` against at
    import time any more — an unknown key just resolves to "off" at request time, see feature_service.py.
    """

    def dependency(restaurant_id: RestaurantId, db: Annotated[Session, Depends(get_db)]) -> None:
        FeatureService(db).require(restaurant_id, key)

    return dependency


def requires_feature_for_user(key: str) -> Callable[..., None]:
    """Route dependency for signed-in customer routes: 403 when the flag is off for the caller's own restaurant."""

    def dependency(user: CurrentUser, db: Annotated[Session, Depends(get_db)]) -> None:
        if user.restaurant_id is None:
            raise ForbiddenError("This feature is not available for this account")
        FeatureService(db).require(user.restaurant_id, key)

    return dependency


def requires_feature_for_device(key: str) -> Callable[..., None]:
    """Route dependency for POS routes: 403 when the flag is off for the paired device's restaurant.

    Same core check as the two variants above — only the identity source differs, since a POS device
    has no CurrentUser (JWT) to resolve a restaurant from."""

    def dependency(device: CurrentDevice, db: Annotated[Session, Depends(get_db)]) -> None:
        FeatureService(db).require(device.device.restaurant_id, key)

    return dependency


def requires_feature_for_pos_staff(key: str) -> Callable[..., None]:
    """Route dependency for POS routes gated on a PIN'd-in staff member (CurrentPosStaff), not just
    the device itself — e.g. order-taking, which needs to know who's acting, not only which till."""

    def dependency(staff: CurrentPosStaff, db: Annotated[Session, Depends(get_db)]) -> None:
        FeatureService(db).require(staff.device.restaurant_id, key)

    return dependency
