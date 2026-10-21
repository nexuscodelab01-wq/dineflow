"""Stripe Connect onboarding schemas."""

from decimal import Decimal

from pydantic import BaseModel


class StripeOnboardLink(BaseModel):
    url: str


class TaxCheckRead(BaseModel):
    """Result of a dry-run tax calculation for the restaurant's own address."""

    mode: str  # FLAT | STRIPE — what is actually in effect
    ok: bool
    rate_percent: Decimal | None = None
    message: str


class StripeStatus(BaseModel):
    connected: bool
    charges_enabled: bool
