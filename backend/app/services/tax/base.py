"""The tax seam — mirrors `app/services/payments/`: order logic asks a TaxCalculator for a quote and never
knows whether it came from a flat rate or Stripe Tax."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class TaxLine:
    reference: str
    amount: Decimal  # post-discount, tax-exclusive
    tax_code: str | None = None


@dataclass
class TaxLocation:
    """Where the sale happens: the delivery address, else the restaurant itself."""

    country: str
    state: str | None = None
    postal_code: str | None = None
    city: str | None = None
    line1: str | None = None


@dataclass
class TaxQuote:
    tax_total: Decimal
    # tax per TaxLine.reference, summing exactly to tax_total
    line_tax: dict[str, Decimal] = field(default_factory=dict)
    calculation_id: str | None = None
    # Stripe says it isn't collecting tax at this location (no registration) — worth telling the owner.
    not_collecting: bool = False
    rate_percent: Decimal | None = None


class TaxCalculator(ABC):
    @abstractmethod
    def quote(self, lines: list[TaxLine], *, location: TaxLocation, shipping: Decimal, currency: str) -> TaxQuote:
        ...


def allocate(total: Decimal, weights: list[Decimal]) -> list[Decimal]:
    """Split `total` across `weights` to the cent, the last share absorbing rounding so the parts sum exactly."""
    weight_sum = sum(weights, Decimal(0))
    if not weights:
        return []
    if weight_sum <= 0:
        shares = [Decimal("0.00")] * len(weights)
        shares[-1] = total
        return shares
    shares = [(total * w / weight_sum).quantize(Decimal("0.01")) for w in weights[:-1]]
    shares.append((total - sum(shares, Decimal("0.00"))).quantize(Decimal("0.01")))
    return shares
