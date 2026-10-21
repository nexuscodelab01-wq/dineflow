from decimal import Decimal

from app.services.tax.base import (
    TaxCalculator,
    TaxLine,
    TaxLocation,
    TaxQuote,
    allocate,
)


class FlatTaxCalculator(TaxCalculator):
    """`taxable × Restaurant.tax_rate` — exactly what every site did inline before the seam existed. The
    delivery fee is not taxed (shipping is ignored), matching that behaviour."""

    def __init__(self, rate: Decimal) -> None:
        self.rate = rate

    def quote(self, lines: list[TaxLine], *, location: TaxLocation, shipping: Decimal, currency: str) -> TaxQuote:
        taxable = sum((line.amount for line in lines), Decimal("0.00"))
        tax = (taxable * self.rate).quantize(Decimal("0.01"))
        shares = allocate(tax, [line.amount for line in lines])
        return TaxQuote(
            tax_total=tax, line_tax={line.reference: share for line, share in zip(lines, shares, strict=True)},
            rate_percent=(self.rate * 100).quantize(Decimal("0.001")),
        )
