"""Authentication for a paired POS device, and for whichever staff member has PIN'd into it.

Two layers, matching the table-pass/guest split in dependencies/guest.py: a device token identifies
the *machine* (long-lived, survives restarts), a pos_session token identifies *who's currently using
it* (short-lived, minted on PIN entry). Both get re-checked against the live Device row on every
request — a revoked device's already-issued pos_session tokens die immediately too, not just new
device-token requests, the same way RestaurantUser.is_active is never cached.
"""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import UnauthorizedError
from app.core.security import decode_device_token, decode_pos_session_token
from app.db.session import enter_tenant_mode, get_db
from app.dependencies.auth import bearer_scheme
from app.models.device import Device
from app.models.restaurant_user import RestaurantUser
from app.models.user import User


@dataclass
class PosDevice:
    device: Device


def get_device(
    db: Annotated[Session, Depends(get_db)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> PosDevice:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise UnauthorizedError("Pair this device first")
    try:
        payload = decode_device_token(credentials.credentials)
        device_id, restaurant_id = int(payload["sub"]), int(payload["tenant"])
    except (ValueError, KeyError):
        raise UnauthorizedError("Invalid device pairing") from None
    device = db.get(Device, device_id)
    if device is None or device.restaurant_id != restaurant_id or device.revoked_at is not None:
        raise UnauthorizedError("This device's pairing has been revoked")
    enter_tenant_mode(db, device.restaurant_id)
    return PosDevice(device)


CurrentDevice = Annotated[PosDevice, Depends(get_device)]


@dataclass
class PosStaff:
    device: Device
    user: User
    membership: RestaurantUser


def get_pos_staff(
    db: Annotated[Session, Depends(get_db)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> PosStaff:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise UnauthorizedError("Enter a PIN to continue")
    try:
        payload = decode_pos_session_token(credentials.credentials)
        staff_user_id, device_id, restaurant_id = int(payload["sub"]), int(payload["device"]), int(payload["tenant"])
    except (ValueError, KeyError):
        raise UnauthorizedError("Invalid PIN session") from None
    device = db.get(Device, device_id)
    # Re-checked here too, not just in get_device: a device revoked after this PIN session was minted
    # must stop working immediately, same as RestaurantUser.is_active below.
    if device is None or device.restaurant_id != restaurant_id or device.revoked_at is not None:
        raise UnauthorizedError("This device's pairing has been revoked")
    membership = db.scalar(
        select(RestaurantUser).where(RestaurantUser.user_id == staff_user_id, RestaurantUser.restaurant_id == restaurant_id)
    )
    if membership is None or not membership.is_active:
        raise UnauthorizedError("This staff member no longer has access here")
    user = db.get(User, staff_user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError("This staff member no longer has access here")
    enter_tenant_mode(db, restaurant_id)
    return PosStaff(device, user, membership)


CurrentPosStaff = Annotated[PosStaff, Depends(get_pos_staff)]
