"""Feature flag schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FeatureRead(BaseModel):
    key: str
    description: str
    default: bool
    override: bool | None
    enabled: bool


class FeatureSet(BaseModel):
    enabled: bool


class FeatureCatalogRead(BaseModel):
    """One flag in the global catalog — no restaurant in view, so no override/enabled here."""

    key: str
    description: str
    default: bool


class FeatureCreate(BaseModel):
    key: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=500)
    default: bool = False

    @field_validator("key")
    @classmethod
    def _key_format(cls, value: str) -> str:
        value = value.strip().lower()
        if not value or not value[0].isalpha() or not all(c.isalnum() or c == "_" for c in value):
            raise ValueError("Key must be lowercase letters, numbers and underscores, starting with a letter")
        return value


class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    restaurant_id: int | None
    actor_label: str
    action: str
    target: str | None
    details: dict[str, Any]
    created_at: datetime
