"""Feature flags, declared in code.

Add a flag here (key, default, one-line description) and gate the code with `requires_feature(key)` on
the API and `useFeature(key)` in the frontend. A restaurant can deviate from the default through a
database override, set by a platform admin (`PUT /platform/restaurants/{id}/features/{key}` or the
`python -m app.cli` script). Removing a flag from this list makes any leftover overrides inert.

Keep flags short-lived: once a feature is on for everyone, delete the flag and the checks.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Feature:
    default: bool
    description: str


FEATURES: dict[str, Feature] = {
    "reservations": Feature(True, "Guests can book tables; staff manage bookings"),
    "qr_table_ordering": Feature(False, "Guests order and pay from a QR code at their table"),
    "pay_at_table": Feature(False, "Guests split and pay the bill from their phone"),
    "kitchen_v2": Feature(False, "New kitchen display with stations and course timing"),
    "custom_branding": Feature(False, "Restaurant's own logo, colours and fonts on its site"),
    "reviews": Feature(False, "Guests can rate and review a completed visit; shown on the site"),
    "loyalty": Feature(False, "Customers earn points on completed orders and can view their balance"),
    "coupons": Feature(False, "Discount codes customers can apply at checkout"),
    "scheduled_orders": Feature(False, "Customers can order ahead for a later collection slot"),
}
