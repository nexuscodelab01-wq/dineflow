"""Feature flag schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class FeatureRead(BaseModel):
    key: str
    description: str
    default: bool
    override: bool | None
    enabled: bool


class FeatureSet(BaseModel):
    enabled: bool


class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    restaurant_id: int | None
    actor_label: str
    action: str
    target: str | None
    details: dict[str, Any]
    created_at: datetime
