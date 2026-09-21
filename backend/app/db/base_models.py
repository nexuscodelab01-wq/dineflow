"""Import all models here so Alembic can discover metadata."""

from app.db.base import Base
from app.models import (  # noqa: F401
    Address,
    AuditLog,
    Category,
    FeatureOverride,
    Job,
    MenuItem,
    MenuItemModifier,
    MenuModifier,
    MenuModifierOption,
    Order,
    OrderItem,
    OrderItemModifier,
    OrderStatusHistory,
    Payment,
    RefreshToken,
    Reservation,
    Restaurant,
    RestaurantTable,
    RestaurantUser,
    Role,
    ServiceRequest,
    SessionGuest,
    TableSession,
    User,
)

__all__ = ["Base"]
