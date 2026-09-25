"""Restaurant staff: invite, list, and change a membership's role or whether it's active.

An invite reuses `PasswordService.issue_link` (already used for the owner created at provisioning
time and for password resets) rather than inventing a second mechanism — a staff invite email is a
"set your password" email that happens to also be the first time this person can sign in at all.
"""

import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.core.security import hash_password
from app.models.enums import RoleName
from app.models.password_reset_token import INVITE, PasswordResetToken
from app.models.restaurant import Restaurant
from app.models.restaurant_user import RestaurantUser
from app.models.role import Role
from app.models.user import User
from app.repositories.restaurant import RestaurantRepository
from app.repositories.user import UserRepository
from app.schemas.staff import StaffInvite, StaffInviteRead, StaffRead, StaffUpdate
from app.services.password_service import PasswordService


class StaffService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.users = UserRepository(db)
        self.restaurants = RestaurantRepository(db)
        self.passwords = PasswordService(db)

    def _restaurant(self, restaurant_id: int) -> Restaurant:
        restaurant = self.restaurants.get_by_id(restaurant_id)
        if restaurant is None:
            raise NotFoundError("Restaurant not found")
        return restaurant

    # ------------------------------------------------------------------ reading

    def _invite_accepted(self, user_id: int) -> bool:
        """True once the invite link that created this account (or the most recent one) has been used.
        A pending invite has no used_at yet on its INVITE-purpose token."""
        pending = self.db.scalar(
            select(PasswordResetToken.id).where(
                PasswordResetToken.user_id == user_id,
                PasswordResetToken.purpose == INVITE,
                PasswordResetToken.used_at.is_(None),
            ).limit(1)
        )
        return pending is None

    def _to_read(self, membership: RestaurantUser) -> StaffRead:
        return StaffRead(
            id=membership.id, user_id=membership.user_id, email=membership.user.email,
            first_name=membership.user.first_name, last_name=membership.user.last_name,
            role=RoleName(membership.role), is_active=membership.is_active,
            created_at=membership.created_at, invite_accepted=self._invite_accepted(membership.user_id),
        )

    def list_for_restaurant(self, restaurant_id: int) -> list[StaffRead]:
        memberships = self.db.scalars(
            select(RestaurantUser).where(RestaurantUser.restaurant_id == restaurant_id)
            .order_by(RestaurantUser.created_at)
        ).all()
        return [self._to_read(m) for m in memberships]

    def _get(self, membership_id: int, restaurant_id: int) -> RestaurantUser:
        membership = self.db.get(RestaurantUser, membership_id)
        if membership is None or membership.restaurant_id != restaurant_id:
            raise NotFoundError("Staff member not found")
        return membership

    def _active_admin_count(self, restaurant_id: int, *, excluding: int | None = None) -> int:
        stmt = select(RestaurantUser.id).where(
            RestaurantUser.restaurant_id == restaurant_id,
            RestaurantUser.role == RoleName.RESTAURANT_ADMIN.value,
            RestaurantUser.is_active.is_(True),
        )
        if excluding is not None:
            stmt = stmt.where(RestaurantUser.id != excluding)
        return len(self.db.scalars(stmt).all())

    def _sync_global_role(self, user: User) -> None:
        """Authorization today runs on the account's *global* role (`app/dependencies/restaurant.py`),
        not on a membership's per-restaurant role — see the model's docstring. Without this, promoting
        someone to RESTAURANT_ADMIN at one restaurant would show them as an admin while every
        admin-only endpoint kept refusing them: a silently broken feature, not just an unwired seam.

        Promote-only, deliberately. By the time any staff route runs, the request is already in tenant
        mode for one restaurant (`get_restaurant_id` → `enter_tenant_mode`), so row-level security
        restricts every query here — including this one — to that restaurant's rows. There is no way
        to ask "is this person still an admin at some *other* restaurant" from inside a tenant-scoped
        request, so demoting can't be done safely here: it would risk stripping access this same
        person still legitimately holds elsewhere, invisibly to this query. Granting has no such
        problem — the membership that justifies it is the very row this request is already scoped to.
        A platform admin (SUPER_ADMIN) is never touched; they hold no restaurant membership to read.
        """
        current = user.role.name.value if hasattr(user.role.name, "value") else str(user.role.name)
        if current in (RoleName.SUPER_ADMIN.value, RoleName.RESTAURANT_ADMIN.value):
            return
        is_admin_here = self.db.scalar(
            select(RestaurantUser.id).where(
                RestaurantUser.user_id == user.id, RestaurantUser.role == RoleName.RESTAURANT_ADMIN.value,
                RestaurantUser.is_active.is_(True),
            ).limit(1)
        ) is not None
        if not is_admin_here:
            return
        role_row = self.db.scalar(select(Role).where(Role.name == RoleName.RESTAURANT_ADMIN.value))
        user.role_id = role_row.id

    # ------------------------------------------------------------------ inviting

    def invite(self, restaurant_id: int, data: StaffInvite, actor: User) -> StaffInviteRead:
        restaurant = self._restaurant(restaurant_id)
        existing_membership = self.db.scalar(
            select(RestaurantUser).join(User, User.id == RestaurantUser.user_id).where(
                RestaurantUser.restaurant_id == restaurant.id, User.email == data.email.lower(),
            )
        )
        if existing_membership is not None:
            raise ConflictError("This person is already staff here")

        user = self.users.get_by_email(data.email, restaurant_id=None)  # a global identity only — never a customer
        if user is not None:
            role_name = user.role.name.value if hasattr(user.role.name, "value") else str(user.role.name)
            if role_name == RoleName.SUPER_ADMIN.value:
                raise AppError("This email belongs to a platform admin account and can't be added as restaurant staff")
        else:
            role_row = self.db.scalar(select(Role).where(Role.name == data.role.value))
            # The account never sees this password: the invite link is the only way in, same as a
            # restaurant's owner at provisioning time (see tenant_provisioning._owner).
            user = self.users.create(
                email=data.email, hashed_password=hash_password(secrets.token_urlsafe(32)),
                first_name=data.first_name, last_name=data.last_name, role_id=role_row.id,
            )

        membership = RestaurantUser(restaurant_id=restaurant.id, user_id=user.id, role=data.role, is_active=True)
        self.db.add(membership)
        self.db.flush()
        self._sync_global_role(user)
        link = self.passwords.issue_link(user, restaurant, invite=True, send=True)
        self.db.commit()
        self.db.refresh(membership)
        read = self._to_read(membership)
        return StaffInviteRead(**read.model_dump(), invite_link=link)

    def resend_invite(self, membership_id: int, restaurant_id: int) -> str:
        restaurant = self._restaurant(restaurant_id)
        membership = self._get(membership_id, restaurant_id)
        if self._invite_accepted(membership.user_id):
            raise AppError("This person already set their password — there's no invite to resend")
        return self.passwords.issue_link(membership.user, restaurant, invite=True, send=True)

    # ------------------------------------------------------------------ changing

    def update(self, membership_id: int, restaurant_id: int, data: StaffUpdate, actor: User) -> StaffRead:
        membership = self._get(membership_id, restaurant_id)
        is_self = membership.user_id == actor.id

        next_role = data.role if data.role is not None else RoleName(membership.role)
        next_active = data.is_active if data.is_active is not None else membership.is_active
        losing_admin = (
            RoleName(membership.role) == RoleName.RESTAURANT_ADMIN
            and membership.is_active
            and (next_role != RoleName.RESTAURANT_ADMIN or not next_active)
        )
        if losing_admin:
            if is_self:
                raise AppError("You can't remove your own admin access — ask another admin to do it")
            if self._active_admin_count(restaurant_id, excluding=membership.id) == 0:
                raise AppError("This restaurant would be left with no active admin")

        if data.role is not None:
            membership.role = data.role
        if data.is_active is not None:
            membership.is_active = data.is_active
        self.db.flush()
        self._sync_global_role(membership.user)
        self.db.commit()
        self.db.refresh(membership)
        return self._to_read(membership)
