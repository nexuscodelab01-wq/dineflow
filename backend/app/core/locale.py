"""Countries and currencies a restaurant can run in — the one place to extend when a market is added.

US + Canada only for now (both 2-decimal currencies). `_minor_units` in the Stripe provider assumes two
decimals, so a zero-/three-decimal currency (jpy, kwd) must fix that first before being added here.
"""

from decimal import Decimal

COUNTRY_CURRENCY: dict[str, str] = {"US": "usd", "CA": "cad"}
SUPPORTED_COUNTRIES = frozenset(COUNTRY_CURRENCY)
SUPPORTED_CURRENCIES = frozenset(COUNTRY_CURRENCY.values())


# Stripe Tax product tax codes a menu item can carry (txcd_… ids from Stripe's tax-categories list).
TAX_CODES: dict[str, str] = {
    "txcd_40060003": "Prepared food (eat-in / hot food)",
    "txcd_40040000": "Grocery / packaged food (non-immediate)",
    "txcd_40040021": "Plain bread",
    "txcd_41020001": "Alcohol — beer",
    "txcd_41020002": "Alcohol — spirits",
    "txcd_41020003": "Alcohol — wine",
}
DEFAULT_TAX_CODE = "txcd_40060003"
SHIPPING_TAX_CODE = "txcd_92010001"


def format_money(amount: Decimal | float | str, currency: str) -> str:
    """`$12.50` for usd, `$12.50 CAD` for cad — the suffix keeps the two dollars apart in plain text."""
    text = f"${Decimal(str(amount)):.2f}"
    return text if currency.lower() == "usd" else f"{text} {currency.upper()}"
