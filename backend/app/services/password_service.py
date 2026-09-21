"""Forgotten and changed passwords: emailed single-use links, and changing it while signed in."""

import hashlib
import logging
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.core.security import hash_password, verify_password
from app.core.tenancy import site_url
from app.models.password_reset_token import INVITE, RESET, PasswordResetToken
from app.models.restaurant import Restaurant
from app.models.user import User
from app.repositories.refresh_token import RefreshTokenRepository
from app.repositories.user import UserRepository
from app.schemas.auth import password_problem
from app.services.notifications import notify_password_changed, notify_password_reset

logger = logging.getLogger(__name__)

RESET_HOURS = 1
INVITE_HOURS = 24 * 7
MAX_LINKS_PER_HOUR = 3  # per account: stops someone flooding a person's inbox


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class PasswordService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.users = UserRepository(db)
        self.sessions = RefreshTokenRepository(db)

    # ------------------------------------------------------------------ links

    def issue_link(self, user: User, restaurant: Restaurant | None, *, invite: bool = False, send: bool = True) -> str:
        """Create a single-use link for this user. Only its hash is stored; the address is returned (and emailed)."""
        raw = secrets.token_urlsafe(32)
        hours = INVITE_HOURS if invite else RESET_HOURS
        record = PasswordResetToken(
            user_id=user.id, restaurant_id=restaurant.id if restaurant else None, token_hash=_hash(raw),
            purpose=INVITE if invite else RESET, expires_at=datetime.now(UTC) + timedelta(hours=hours),
        )
        self.db.add(record)
        self.db.flush()
        link = f"{site_url(restaurant)}/reset-password?token={raw}"
        if send:
            notify_password_reset(self.db, restaurant, user.email, user.first_name, link, record.id, invite=invite, hours=hours)
        return link

    def request_reset(self, email: str, restaurant_id: int | None) -> None:
        """Email a reset link if this identity exists. Says nothing either way, so it cannot be used to find out
        who has an account."""
        restaurant = self.db.get(Restaurant, restaurant_id) if restaurant_id is not None else None
        if restaurant_id is not None and (restaurant is None or not restaurant.is_active):
            return
        user = self.users.get_by_email(email, restaurant_id)
        if user is None or not user.is_active:
            return
        recent = self.db.scalars(
            select(PasswordResetToken.id).where(
                PasswordResetToken.user_id == user.id, PasswordResetToken.created_at > datetime.now(UTC) - timedelta(hours=1))
        ).all()
        if len(recent) >= MAX_LINKS_PER_HOUR:
            logger.info("Password reset throttled: user_id=%s", user.id)
            return
        self.issue_link(user, restaurant)
        self.db.commit()
        logger.info("Password reset requested: user_id=%s", user.id)

    # ------------------------------------------------------------------ using a link

    def reset(self, token: str, new_password: str) -> None:
        record = self.db.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash == _hash(token)))
        now = datetime.now(UTC)
        if record is None or record.used_at is not None or record.expires_at <= now:
            raise AppError("This link is invalid or has expired. Please ask for a new one.")
        user = self.users.get_by_id(record.user_id)
        if user is None or not user.is_active:
            raise AppError("This link is invalid or has expired. Please ask for a new one.")
        problem = password_problem(new_password, user.email)
        if problem:
            raise AppError(problem)

        user.hashed_password = hash_password(new_password)
        self.db.execute(  # this link and any other still-open ones are spent
            update(PasswordResetToken).where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None)).values(used_at=now)
        )
        self.sessions.revoke_all_for_user(user.id)  # anyone signed in with the old password is signed out
        restaurant = self.db.get(Restaurant, record.restaurant_id) if record.restaurant_id else None
        notify_password_changed(self.db, restaurant, user.email, user.first_name, f"reset:{record.id}")
        self.db.commit()
        logger.info("Password reset completed: user_id=%s", user.id)

    # ------------------------------------------------------------------ signed in

    def change(self, user: User, current_password: str, new_password: str) -> None:
        if not verify_password(current_password, user.hashed_password):
            # 400, not 401: the person *is* signed in. A 401 would make the app think the session expired and sign them out.
            raise AppError("Your current password is not right")
        if verify_password(new_password, user.hashed_password):
            raise AppError("Choose a password you have not used just now")
        problem = password_problem(new_password, user.email)
        if problem:
            raise AppError(problem)
        user.hashed_password = hash_password(new_password)
        self.sessions.revoke_all_for_user(user.id)
        restaurant = self.db.get(Restaurant, user.restaurant_id) if user.restaurant_id else None
        notify_password_changed(self.db, restaurant, user.email, user.first_name, f"change:{user.id}:{int(datetime.now(UTC).timestamp())}")
        self.db.commit()
        logger.info("Password changed: user_id=%s", user.id)
