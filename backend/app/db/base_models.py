"""Import all models here so Alembic can discover metadata."""

from app.db.base import Base
from app.models import (  # noqa: F401
    Address,
    Category,
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
    Restaurant,
    RestaurantTable,
    RestaurantUser,
    Role,
    User,
)

__all__ = ["Base"]
