"""Countries and currencies a restaurant can run in — the one place to extend when a market is added.

US + Canada only for now (both 2-decimal currencies). `_minor_units` in the Stripe provider assumes two
decimals, so a zero-/three-decimal currency (jpy, kwd) must fix that first before being added here.
"""

from decimal import Decimal

COUNTRY_CURRENCY: dict[str, str] = {"US": "usd", "CA": "cad"}
SUPPORTED_COUNTRIES = frozenset(COUNTRY_CURRENCY)
SUPPORTED_CURRENCIES = frozenset(COUNTRY_CURRENCY.values())


def format_money(amount: Decimal | float | str, currency: str) -> str:
    """`$12.50` for usd, `$12.50 CAD` for cad — the suffix keeps the two dollars apart in plain text."""
    text = f"${Decimal(str(amount)):.2f}"
    return text if currency.lower() == "usd" else f"{text} {currency.upper()}"
