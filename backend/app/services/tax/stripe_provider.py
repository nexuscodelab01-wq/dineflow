"""Stripe Tax via the standalone Calculations + Transactions APIs, on the restaurant's own connected account
(the restaurant is the merchant, so tax registrations live there). Calculation is a read-only quote; the
sale is recorded as a Transaction only once it's paid, and reversed on refund."""

import logging
from decimal import Decimal

import stripe
from stripe.params.tax import (
    CalculationCreateParams,
    CalculationCreateParamsCustomerDetailsAddress,
    CalculationCreateParamsLineItem,
)

from app.core.config import settings
from app.core.locale import SHIPPING_TAX_CODE
from app.services.tax.base import (
    TaxCalculator,
    TaxLine,
    TaxLocation,
    TaxQuote,
    allocate,
)

logger = logging.getLogger(__name__)


def _minor(amount: Decimal) -> int:
    return int((amount * 100).to_integral_value())


class StripeTaxCalculator(TaxCalculator):
    def __init__(self, connected_account_id: str, fallback: TaxCalculator) -> None:
        self.account = connected_account_id
        self.fallback = fallback
        self.client = stripe.StripeClient(settings.STRIPE_SECRET_KEY)

    def quote(self, lines: list[TaxLine], *, location: TaxLocation, shipping: Decimal, currency: str) -> TaxQuote:
        billable = [line for line in lines if line.amount > 0]
        if not billable and shipping <= 0:
            return self.fallback.quote(lines, location=location, shipping=shipping, currency=currency)
        try:
            return self._calculate(lines, billable, location, shipping, currency)
        except stripe.StripeError as exc:
            # An outage or misconfiguration must not stop the restaurant taking orders.
            logger.warning("Stripe Tax failed (%s); falling back to the flat rate", exc)
            return self.fallback.quote(lines, location=location, shipping=shipping, currency=currency)

    def _calculate(self, lines: list[TaxLine], billable: list[TaxLine], location: TaxLocation, shipping: Decimal, currency: str) -> TaxQuote:
        address: CalculationCreateParamsCustomerDetailsAddress = {"country": location.country}
        if location.state:
            address["state"] = location.state
        if location.postal_code:
            address["postal_code"] = location.postal_code
        if location.city:
            address["city"] = location.city
        if location.line1:
            address["line1"] = location.line1
        line_items: list[CalculationCreateParamsLineItem] = []
        for line in billable:
            item: CalculationCreateParamsLineItem = {"amount": _minor(line.amount), "reference": line.reference}
            if line.tax_code:
                item["tax_code"] = line.tax_code
            line_items.append(item)
        params: CalculationCreateParams = {
            "currency": currency,
            "customer_details": {"address": address, "address_source": "shipping"},
            "line_items": line_items,
        }
        if shipping > 0:
            params["shipping_cost"] = {"amount": _minor(shipping), "tax_code": SHIPPING_TAX_CODE}
        calc = self.client.v1.tax.calculations.create(params, options={"stripe_account": self.account})
        total = Decimal(calc.tax_amount_exclusive) / 100
        # Stripe's tax_amount_exclusive includes tax on shipping; the order stores one tax figure, so the
        # shipping share is attributed to the item lines proportionally (the sum is what matters).
        shares = allocate(total, [line.amount for line in lines])
        breakdown = calc.tax_breakdown or []
        not_collecting = total == 0 and any(b.taxability_reason == "not_collecting" for b in breakdown)
        rate = None
        taxable = sum((line.amount for line in billable), Decimal(0)) + shipping
        if taxable > 0:
            rate = (total / taxable * 100).quantize(Decimal("0.001"))
        return TaxQuote(
            tax_total=total, line_tax={line.reference: share for line, share in zip(lines, shares, strict=True)},
            calculation_id=calc.id, not_collecting=not_collecting, rate_percent=rate,
        )


def record_transaction(connected_account_id: str, calculation_id: str, reference: str) -> str | None:
    """Record a paid sale for the owner's tax reports. Best-effort: a Stripe hiccup must not undo a payment."""
    try:
        client = stripe.StripeClient(settings.STRIPE_SECRET_KEY)
        tx = client.v1.tax.transactions.create_from_calculation(
            {"calculation": calculation_id, "reference": reference},
            options={"stripe_account": connected_account_id, "idempotency_key": f"taxtx-{reference}"},
        )
        return tx.id
    except stripe.StripeError as exc:
        logger.warning("Could not record tax transaction for %s: %s", reference, exc)
        return None


def reverse_transaction(connected_account_id: str, transaction_id: str, reference: str) -> None:
    try:
        client = stripe.StripeClient(settings.STRIPE_SECRET_KEY)
        client.v1.tax.transactions.create_reversal(
            {"mode": "full", "original_transaction": transaction_id, "reference": f"{reference}-refund"},
            options={"stripe_account": connected_account_id, "idempotency_key": f"taxrev-{reference}"},
        )
    except stripe.StripeError as exc:
        logger.warning("Could not reverse tax transaction %s: %s", transaction_id, exc)
