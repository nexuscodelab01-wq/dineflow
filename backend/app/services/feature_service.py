"""The feature flag catalog, per-restaurant overrides, and the audit trail.

The catalog itself (`Feature`, the `features` table) is database-backed, not a hardcoded dict — a
platform admin creates and deletes flags from the console (or the CLI). This means **the code can no
longer tell a real programmer typo apart from "nobody's created this flag yet" or "an admin removed
it"**: there is no static list left to check a key against at import time. So `is_enabled`/`require`
fail *closed* (treat an unknown key as disabled) rather than raising — a crash would be worse than a
feature silently staying off. The cost: if a flag that's still checked somewhere in code gets deleted,
that check now just always denies, with nothing to point at why. Always create the DB flag before
shipping a new `requires_feature(key)` call, never after.
"""

import re

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.exceptions import AppError, ConflictError, ForbiddenError, NotFoundError
from app.models.audit_log import AuditLog
from app.models.feature import Feature
from app.models.feature_override import FeatureOverride
from app.models.restaurant import Restaurant
from app.models.user import User

KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")

# The flags DineFlow shipped with code checks for, before the catalog moved to the database — seeded
# idempotently so a fresh install (or an existing one) ends up with these even though nothing inserts
# them via a migration. Ordinary catalog rows after that: editable and deletable like any other.
_DEFAULTS: dict[str, tuple[str, bool]] = {
    "reservations": ("Guests can book tables; staff manage bookings", True),
    "qr_table_ordering": ("Guests order and pay from a QR code at their table", False),
    "pay_at_table": ("Guests split and pay the bill from their phone", False),
    "kitchen_v2": ("New kitchen display with stations and course timing", False),
    "custom_branding": ("Restaurant's own logo, colours and fonts on its site", False),
    "reviews": ("Guests can rate and review a completed visit; shown on the site", False),
    "loyalty": ("Customers earn points on completed orders and can view their balance", False),
    "coupons": ("Discount codes customers can apply at checkout", False),
    "scheduled_orders": ("Customers can order ahead for a later collection slot", False),
}


class FeatureService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------ the catalog itself

    def ensure_defaults(self) -> None:
        """Idempotent — same pattern as RoleRepository.ensure_defaults(), called from db/seed.py and
        tests/conftest.py. Never overwrites a flag an admin has since edited or already has in place."""
        existing = set(self.db.scalars(select(Feature.key)))
        for key, (description, default_enabled) in _DEFAULTS.items():
            if key not in existing:
                self.db.add(Feature(key=key, description=description, default_enabled=default_enabled))
        self.db.flush()

    def catalog(self) -> list[Feature]:
        return list(self.db.scalars(select(Feature).order_by(Feature.key)))

    def create_flag(self, key: str, description: str, default_enabled: bool, actor: User) -> Feature:
        key = key.strip().lower()
        if not KEY_RE.match(key) or len(key) > 64:
            raise AppError("Key must be lowercase letters, numbers and underscores, starting with a letter")
        if self.db.get(Feature, key) is not None:
            raise ConflictError(f"A flag named '{key}' already exists")
        feature = Feature(key=key, description=description.strip(), default_enabled=default_enabled)
        self.db.add(feature)
        self.db.add(AuditLog(restaurant_id=None, actor_user_id=actor.id, actor_label=actor.email, action="feature.created", target=key))
        self.db.commit()
        return feature

    def delete_flag(self, key: str, actor: User) -> None:
        feature = self.db.get(Feature, key)
        if feature is None:
            raise NotFoundError("Flag not found")
        self.db.execute(delete(FeatureOverride).where(FeatureOverride.key == key))
        self.db.delete(feature)
        self.db.add(AuditLog(restaurant_id=None, actor_user_id=actor.id, actor_label=actor.email, action="feature.deleted", target=key))
        self.db.commit()

    # ------------------------------------------------------------------ reading, per restaurant

    def overrides(self, restaurant_id: int, *, known: set[str] | None = None) -> dict[str, bool]:
        known = {f.key for f in self.catalog()} if known is None else known
        rows = self.db.execute(
            select(FeatureOverride.key, FeatureOverride.enabled).where(FeatureOverride.restaurant_id == restaurant_id)
        ).all()
        return {key: enabled for key, enabled in rows if key in known}  # ignore flags since deleted from the catalog

    def resolve(self, restaurant_id: int) -> dict[str, bool]:
        """Every flag's effective value for this restaurant."""
        catalog = self.catalog()
        overrides = self.overrides(restaurant_id, known={f.key for f in catalog})
        return {feature.key: overrides.get(feature.key, feature.default_enabled) for feature in catalog}

    def is_enabled(self, restaurant_id: int, key: str) -> bool:
        return self.resolve(restaurant_id).get(key, False)  # no catalog row -> treat as off, see module docstring

    def require(self, restaurant_id: int, key: str) -> None:
        if not self.is_enabled(restaurant_id, key):
            raise ForbiddenError("This feature is not available for this restaurant")

    def listing(self, restaurant_id: int) -> list[dict]:
        catalog = self.catalog()
        overrides = self.overrides(restaurant_id, known={f.key for f in catalog})
        return [
            {
                "key": feature.key,
                "description": feature.description,
                "default": feature.default_enabled,
                "override": overrides.get(feature.key),
                "enabled": overrides.get(feature.key, feature.default_enabled),
            }
            for feature in catalog
        ]

    # ------------------------------------------------------------------ changing, per restaurant

    def set(self, restaurant_id: int, key: str, enabled: bool | None, actor: User | None, actor_label: str | None = None) -> list[dict]:
        """Force a flag on/off for one restaurant, or (enabled=None) go back to the default."""
        self._check(restaurant_id, key)
        before = self.overrides(restaurant_id).get(key)
        if enabled is None:
            self.db.execute(delete(FeatureOverride).where(FeatureOverride.restaurant_id == restaurant_id, FeatureOverride.key == key))
        else:
            row = self.db.scalar(select(FeatureOverride).where(FeatureOverride.restaurant_id == restaurant_id, FeatureOverride.key == key))
            if row is None:
                self.db.add(FeatureOverride(restaurant_id=restaurant_id, key=key, enabled=enabled))
            else:
                row.enabled = enabled
        if before != enabled:  # no-op changes are not history
            self.db.add(AuditLog(
                restaurant_id=restaurant_id,
                actor_user_id=actor.id if actor else None,
                actor_label=actor.email if actor else (actor_label or "system"),
                action="feature.reset" if enabled is None else "feature.set",
                target=key,
                details={"before": before, "after": enabled},
            ))
        self.db.commit()
        return self.listing(restaurant_id)

    def audit_log(self, restaurant_id: int | None = None, limit: int = 50) -> list[AuditLog]:
        stmt = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)
        if restaurant_id is not None:
            stmt = stmt.where(AuditLog.restaurant_id == restaurant_id)
        return list(self.db.scalars(stmt).all())

    def _check(self, restaurant_id: int, key: str) -> None:
        if self.db.get(Feature, key) is None:
            raise AppError(f"Unknown feature '{key}'")
        if self.db.get(Restaurant, restaurant_id) is None:
            raise NotFoundError("Restaurant not found")
