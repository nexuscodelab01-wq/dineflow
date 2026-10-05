"""The catalog of feature flags: what flags exist, and their description/default.

A platform-wide reference table, like `Role` — no restaurant_id, no row-level security (see migration
0013's `roles` precedent). Created and deleted by a platform admin from the console (or the CLI); a
restaurant's own choice to deviate from `default_enabled` lives separately, in `FeatureOverride`.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Feature(Base):
    __tablename__ = "features"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    default_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
