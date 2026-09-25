"""Staff membership Pydantic schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.enums import RoleName

# A membership only ever holds one of these two — CUSTOMER and SUPER_ADMIN never get a restaurant_users row.
STAFF_ROLES = {RoleName.RESTAURANT_ADMIN, RoleName.RESTAURANT_STAFF}


def _check_staff_role(value: RoleName) -> RoleName:
    if value not in STAFF_ROLES:
        raise ValueError("role must be RESTAURANT_ADMIN or RESTAURANT_STAFF")
    return value


class StaffInvite(BaseModel):
    email: EmailStr
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    role: RoleName = RoleName.RESTAURANT_STAFF

    @field_validator("role")
    @classmethod
    def _role(cls, value: RoleName) -> RoleName:
        return _check_staff_role(value)


class StaffUpdate(BaseModel):
    """Change a membership's role and/or whether it's active. Both optional; send only what changed."""

    role: RoleName | None = None
    is_active: bool | None = None

    @field_validator("role")
    @classmethod
    def _role(cls, value: RoleName | None) -> RoleName | None:
        return value if value is None else _check_staff_role(value)


class StaffRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int  # the membership id — what you act on (deactivate, change role)
    user_id: int
    email: str
    first_name: str
    last_name: str
    role: RoleName
    is_active: bool
    created_at: datetime
    # A brand-new invite hasn't been opened yet — accepted the moment they set a password (the account
    # was created without one, so a still-unusable login and an unaccepted invite are the same thing).
    invite_accepted: bool


class StaffInviteRead(StaffRead):
    invite_link: str  # shown once, right after inviting — not retrievable again (only its hash is stored)
