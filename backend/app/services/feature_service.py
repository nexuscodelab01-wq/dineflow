"""Reading and changing feature flags, with an audit trail."""

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.exceptions import AppError, ForbiddenError, NotFoundError
from app.core.features import FEATURES
from app.models.audit_log import AuditLog
from app.models.feature_override import FeatureOverride
from app.models.restaurant import Restaurant
from app.models.user import User


class FeatureService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------ reading

    def overrides(self, restaurant_id: int) -> dict[str, bool]:
        rows = self.db.execute(
            select(FeatureOverride.key, FeatureOverride.enabled).where(FeatureOverride.restaurant_id == restaurant_id)
        ).all()
        return {key: enabled for key, enabled in rows if key in FEATURES}  # ignore flags removed from the code

    def resolve(self, restaurant_id: int) -> dict[str, bool]:
        """Every flag's effective value for this restaurant."""
        overrides = self.overrides(restaurant_id)
        return {key: overrides.get(key, feature.default) for key, feature in FEATURES.items()}

    def is_enabled(self, restaurant_id: int, key: str) -> bool:
        if key not in FEATURES:
            raise KeyError(f"Unknown feature flag: {key}")  # a typo in code, not a user error
        return self.resolve(restaurant_id)[key]

    def require(self, restaurant_id: int, key: str) -> None:
        if not self.is_enabled(restaurant_id, key):
            raise ForbiddenError("This feature is not available for this restaurant")

    def listing(self, restaurant_id: int) -> list[dict]:
        overrides = self.overrides(restaurant_id)
        return [
            {
                "key": key,
                "description": feature.description,
                "default": feature.default,
                "override": overrides.get(key),
                "enabled": overrides.get(key, feature.default),
            }
            for key, feature in FEATURES.items()
        ]

    # ------------------------------------------------------------------ changing

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
        if key not in FEATURES:
            raise AppError(f"Unknown feature '{key}'. Known: {', '.join(FEATURES)}")
        if self.db.get(Restaurant, restaurant_id) is None:
            raise NotFoundError("Restaurant not found")
