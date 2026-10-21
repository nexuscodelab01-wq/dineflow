"""What each role may do at the POS, and the reason codes a void / comp / discount / refund must carry.

Admins can do everything. A staff member can do what the restaurant's `pos_staff_permissions` allows; for the rest
they ask a manager, who enters their own PIN to approve that one action (see PosControlService.authorize)."""

from app.models.enums import RoleName

ACTIONS = ("void", "comp", "discount", "refund")

DEFAULT_STAFF_PERMISSIONS: dict[str, object] = {"void": False, "comp": False, "refund": False, "discount_max_pct": 10}

REASONS: dict[str, dict[str, str]] = {
    "VOID": {
        "WRONG_ITEM": "Rung in by mistake", "CHANGED_MIND": "Guest changed their mind", "KITCHEN_ERROR": "Kitchen error",
        "OUT_OF_STOCK": "Item ran out", "OTHER": "Other (note required)",
    },
    "COMP": {
        "SERVICE_RECOVERY": "Service recovery", "MANAGER_COMP": "Manager's comp", "STAFF_MEAL": "Staff meal",
        "PROMO": "Promotion", "OTHER": "Other (note required)",
    },
    "DISCOUNT": {
        "LOYALTY": "Regular / loyalty", "PROMO": "Promotion", "MANAGER": "Manager's discount", "OTHER": "Other (note required)",
    },
    "REFUND": {
        "WRONG_ORDER": "Wrong order", "QUALITY": "Food quality", "DUPLICATE": "Charged twice", "OTHER": "Other (note required)",
    },
}


def role_may(role: RoleName, staff_permissions: dict, action: str, percent: float | None = None) -> bool:
    """Whether someone in `role` may do `action` on their own authority."""
    if role in (RoleName.RESTAURANT_ADMIN, RoleName.SUPER_ADMIN):
        return True
    if action == "discount":
        return percent is not None and percent <= float(staff_permissions.get("discount_max_pct", 0) or 0)
    return bool(staff_permissions.get(action, False))
