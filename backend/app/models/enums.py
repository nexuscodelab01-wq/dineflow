"""Domain enumerations."""

import enum


class RoleName(str, enum.Enum):
    CUSTOMER = "CUSTOMER"
    RESTAURANT_ADMIN = "RESTAURANT_ADMIN"
    RESTAURANT_STAFF = "RESTAURANT_STAFF"
    SUPER_ADMIN = "SUPER_ADMIN"


class OrderType(str, enum.Enum):
    DINE_IN = "DINE_IN"
    PICKUP = "PICKUP"
    DELIVERY = "DELIVERY"


class OrderStatus(str, enum.Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    PREPARING = "PREPARING"
    READY = "READY"
    OUT_FOR_DELIVERY = "OUT_FOR_DELIVERY"
    DELIVERED = "DELIVERED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class TableStatus(str, enum.Enum):
    AVAILABLE = "AVAILABLE"
    OCCUPIED = "OCCUPIED"
    RESERVED = "RESERVED"
    CLEANING = "CLEANING"


class TableShape(str, enum.Enum):
    ROUND = "ROUND"
    SQUARE = "SQUARE"
    RECT = "RECT"


class ReservationStatus(str, enum.Enum):
    HELD = "HELD"
    CONFIRMED = "CONFIRMED"
    SEATED = "SEATED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class WaitlistStatus(str, enum.Enum):
    WAITING = "WAITING"
    NOTIFIED = "NOTIFIED"   # "your table is ready" has been sent
    SEATED = "SEATED"
    CANCELLED = "CANCELLED"


class LoyaltyReason(str, enum.Enum):
    EARNED = "EARNED"      # from a completed order
    REDEEMED = "REDEEMED"  # spent on a discount
    ADJUSTED = "ADJUSTED"  # a staff correction (goodwill, error fix, etc.)


class PaymentStatus(str, enum.Enum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"


class PaymentMethod(str, enum.Enum):
    MOCK = "MOCK"
