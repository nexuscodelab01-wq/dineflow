"""Stripe Connect onboarding schemas."""

from pydantic import BaseModel


class StripeOnboardLink(BaseModel):
    url: str


class StripeStatus(BaseModel):
    connected: bool
    charges_enabled: bool
