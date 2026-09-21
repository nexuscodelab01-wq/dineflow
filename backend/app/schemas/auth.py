"""Authentication and user Pydantic schemas."""

import re

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

# A short list of the passwords attackers try first. Not a substitute for a breach-list check
# (planned), but it stops the most obvious choices.
_COMMON_PASSWORDS = {
    "password", "password1", "password12", "password123", "passw0rd", "12345678", "123456789",
    "1234567890", "qwertyui", "qwerty123", "qwertyuiop", "iloveyou", "admin123", "welcome1",
    "welcome123", "letmein1", "abc12345", "11111111", "00000000", "changeme", "dineflow123",
}


class UserRegister(BaseModel):
    # Customers belong to one restaurant (the site they sign up on).
    restaurant_id: int
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    phone: str | None = Field(default=None, max_length=30)

    @field_validator("password")
    @classmethod
    def _strong_enough(cls, value: str) -> str:
        if not re.search(r"[A-Za-z]", value) or not re.search(r"\d", value):
            raise ValueError("Password must include at least one letter and one number")
        if value.lower() in _COMMON_PASSWORDS:
            raise ValueError("That password is too common — please choose another")
        return value

    @model_validator(mode="after")
    def _not_derived_from_identity(self) -> "UserRegister":
        local_part = str(self.email).split("@", 1)[0].lower()
        if len(local_part) >= 4 and local_part in self.password.lower():
            raise ValueError("Password must not contain your email name")
        return self


class UserLogin(BaseModel):
    email: EmailStr
    password: str
    # The restaurant site being signed in to. Omit for platform / global staff sign-in.
    restaurant_id: int | None = None


class TokenRefresh(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RoleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    first_name: str
    last_name: str
    phone: str | None = None
    is_active: bool
    role: RoleRead
    restaurant_id: int | None = None


class MessageResponse(BaseModel):
    message: str
