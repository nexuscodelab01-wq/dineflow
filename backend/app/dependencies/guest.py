"""Authentication for a device at a table (a guest pass, not an account)."""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.core.exceptions import UnauthorizedError
from app.core.security import decode_guest_token
from app.db.session import get_db
from app.dependencies.auth import bearer_scheme
from app.models.table_session import SessionGuest, TableSession
from app.services.table_session_service import TableSessionService


@dataclass
class TableGuest:
    guest: SessionGuest
    session: TableSession


def get_table_guest(
    db: Annotated[Session, Depends(get_db)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> TableGuest:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise UnauthorizedError("Scan the table's QR code to start")
    try:
        payload = decode_guest_token(credentials.credentials)
        guest_id, session_id, restaurant_id = int(payload["sub"]), int(payload["sess"]), int(payload["tenant"])
    except (ValueError, KeyError):
        raise UnauthorizedError("Invalid table pass") from None
    guest, session = TableSessionService(db).authenticate(guest_id, session_id, restaurant_id)
    return TableGuest(guest, session)


CurrentGuest = Annotated[TableGuest, Depends(get_table_guest)]
