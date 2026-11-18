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


def requires_any_feature(*keys: str) -> Callable[..., None]:
    """Route dependency for staff routes that serve more than one feature (the kitchen and order list are used by online
    ordering, the POS and table ordering alike): 403 only when EVERY one of those channels is off."""

    def dependency(restaurant_id: RestaurantId, db: Annotated[Session, Depends(get_db)]) -> None:
        features = FeatureService(db)
        if not any(features.is_enabled(restaurant_id, key) for key in keys):
            raise ForbiddenError("This feature is not available for this restaurant")

    return dependency


ORDERING_CHANNELS = ("online_ordering", "pos", "qr_table_ordering")


def requires_feature_if_customer(key: str) -> Callable[..., None]:
    """Like requires_feature_for_user, but only judges customers (who belong to one restaurant). A staff or platform identity has
    no restaurant of its own here, so it is left to the route's own rules — which, for these customer-only routes, already
    answer "not found" — instead of getting a different answer from the flag check."""

    def dependency(user: CurrentUser, db: Annotated[Session, Depends(get_db)]) -> None:
        if user.restaurant_id is not None:
            FeatureService(db).require(user.restaurant_id, key)

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
