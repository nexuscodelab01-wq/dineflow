"""User data access."""

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload

from app.models.role import Role
from app.models.user import User


class UserRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, user_id: int) -> User | None:
        stmt = (
            select(User)
            .options(joinedload(User.role))
            .where(User.id == user_id)
        )
        return self.db.scalar(stmt)

    def get_by_email(self, email: str, restaurant_id: int | None = None) -> User | None:
        """The identity that signs in with this email *in this context*.

        With a restaurant: that restaurant's customer, otherwise a global identity (staff / platform admin).
        Without one: global identities only. Customers of other restaurants never match.
        """
        condition = User.restaurant_id.is_(None) if restaurant_id is None else or_(User.restaurant_id == restaurant_id, User.restaurant_id.is_(None))
        stmt = (
            select(User)
            .options(joinedload(User.role))
            .where(User.email == email.lower(), condition)
            .order_by(User.restaurant_id.asc().nulls_last())  # a restaurant's own customer wins over a global identity
            .limit(1)
        )
        return self.db.scalar(stmt)

    def email_taken(self, email: str, restaurant_id: int) -> bool:
        """Is the email already used by a customer of this restaurant, or by a global identity?"""
        return self.db.scalar(
            select(User.id).where(
                User.email == email.lower(),
                or_(User.restaurant_id == restaurant_id, User.restaurant_id.is_(None)),
            ).limit(1)
        ) is not None

    def create(
        self,
        *,
        email: str,
        hashed_password: str,
        first_name: str,
        last_name: str,
        role_id: int,
        phone: str | None = None,
        restaurant_id: int | None = None,
    ) -> User:
        user = User(
            email=email.lower(),
            hashed_password=hashed_password,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            role_id=role_id,
            restaurant_id=restaurant_id,
        )
        self.db.add(user)
        self.db.flush()
        return self.get_by_id(user.id)  # type: ignore[return-value]


class RoleRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_name(self, name: str) -> Role | None:
        return self.db.scalar(select(Role).where(Role.name == name))

    def list_all(self) -> list[Role]:
        return list(self.db.scalars(select(Role).order_by(Role.id)).all())

    def ensure_defaults(self) -> None:
        from app.models.enums import RoleName

        defaults = {
            RoleName.CUSTOMER: "Browse menu and place orders",
            RoleName.RESTAURANT_ADMIN: "Manage restaurant operations",
            RoleName.RESTAURANT_STAFF: "Handle orders and kitchen",
            RoleName.SUPER_ADMIN: "Platform administration",
        }
        for role_name, description in defaults.items():
            existing = self.get_by_name(role_name.value)
            if existing is None:
                self.db.add(Role(name=role_name, description=description))
        self.db.flush()
