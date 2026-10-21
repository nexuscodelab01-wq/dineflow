"""Tax for an order: a pluggable calculator (flat rate, or Stripe Tax per restaurant), plus the helpers the
order / POS / table services share so none of them does tax maths inline."""

from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.locale import DEFAULT_TAX_CODE
from app.models.address import Address
from app.models.order import Order
from app.models.restaurant import Restaurant
from app.services.feature_service import FeatureService
from app.services.tax.base import (
    TaxCalculator,
    TaxLine,
    TaxLocation,
    TaxQuote,
    allocate,
)
from app.services.tax.flat_provider import FlatTaxCalculator

FEATURE = "stripe_tax"


def stripe_tax_active(db: Session, restaurant: Restaurant) -> bool:
    return (
        restaurant.tax_mode == "STRIPE"
        and bool(restaurant.stripe_account_id)
        and settings.PAYMENT_PROVIDER.strip().lower() == "stripe"
        and FeatureService(db).is_enabled(restaurant.id, FEATURE)
    )


def get_tax_calculator(db: Session, restaurant: Restaurant) -> TaxCalculator:
    flat = FlatTaxCalculator(restaurant.tax_rate)
    if stripe_tax_active(db, restaurant):
        from app.services.tax.stripe_provider import (
            StripeTaxCalculator,  # only import stripe if used
        )

        assert restaurant.stripe_account_id is not None
        return StripeTaxCalculator(restaurant.stripe_account_id, flat)
    return flat


def restaurant_location(restaurant: Restaurant) -> TaxLocation:
    return TaxLocation(
        country=restaurant.country, state=restaurant.state, postal_code=restaurant.postal_code,
        city=restaurant.city, line1=restaurant.address,
    )


def address_location(restaurant: Restaurant, address: Address) -> TaxLocation:
    return TaxLocation(
        country=restaurant.country, state=address.state or restaurant.state, postal_code=address.postal_code,
        city=address.city, line1=address.street,
    )


def service_charge_for(restaurant: Restaurant, order_type: object, base: Decimal) -> Decimal:
    """The restaurant's service charge on `base` (post-discount subtotal) for this kind of order, else 0."""
    kind = getattr(order_type, "value", order_type)
    if restaurant.service_charge_rate <= 0 or kind not in (restaurant.service_charge_order_types or []):
        return Decimal("0.00")
    return (base * restaurant.service_charge_rate).quantize(Decimal("0.01"))


def price_order_tax(
    db: Session, restaurant: Restaurant, order: Order, *, discount: Decimal = Decimal("0.00"),
    delivery_fee: Decimal = Decimal("0.00"), location: TaxLocation | None = None,
    taxable_service_charge: Decimal = Decimal("0.00"),
) -> TaxQuote:
    """Tax for `order`'s lines (already added and flushed), after `discount`. Writes each line's tax_code /
    tax_amount snapshot and the calculation id onto the order; the caller sets order.tax from the quote."""
    db.expire(order, ["items"])  # lines were added by order_id; make sure we see them all
    items = list(order.items)
    amounts = [item.line_total for item in items]
    discount = min(discount, sum(amounts, Decimal("0.00")))
    shares = allocate(discount, amounts)
    lines = [
        TaxLine(reference=str(item.id), amount=item.line_total - share, tax_code=item.menu_item.tax_code or restaurant.default_tax_code or DEFAULT_TAX_CODE)
        for item, share in zip(items, shares, strict=True)
    ]
    if taxable_service_charge > 0:
        lines.append(TaxLine(reference="service_charge", amount=taxable_service_charge, tax_code=restaurant.default_tax_code or DEFAULT_TAX_CODE))
    quote = get_tax_calculator(db, restaurant).quote(
        lines, location=location or restaurant_location(restaurant), shipping=delivery_fee, currency=restaurant.currency,
    )
    for item, line in zip(items, lines, strict=False):  # lines may carry one extra (service charge) beyond the items
        item.tax_code = line.tax_code
        item.tax_amount = quote.line_tax.get(line.reference, Decimal("0.00"))
    order.tax_calculation_id = quote.calculation_id
    return quote


def record_paid_order(db: Session, restaurant: Restaurant | None, order: Order) -> None:
    """Report a paid order to Stripe Tax once (cash and card alike — the liability exists either way)."""
    if restaurant is None or not order.tax_calculation_id or order.tax_transaction_id or not restaurant.stripe_account_id:
        return
    from app.services.tax.stripe_provider import record_transaction

    order.tax_transaction_id = record_transaction(restaurant.stripe_account_id, order.tax_calculation_id, order.order_number)


def reverse_paid_order(db: Session, restaurant: Restaurant | None, order: Order) -> None:
    if restaurant is None or not order.tax_transaction_id or not restaurant.stripe_account_id:
        return
    from app.services.tax.stripe_provider import reverse_transaction

    reverse_transaction(restaurant.stripe_account_id, order.tax_transaction_id, order.order_number)


__all__ = [
    "FlatTaxCalculator", "TaxCalculator", "TaxLine", "TaxLocation", "TaxQuote", "address_location",
    "get_tax_calculator", "price_order_tax", "record_paid_order", "restaurant_location",
    "reverse_paid_order", "service_charge_for", "stripe_tax_active",
]
