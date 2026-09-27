"""Stripe Connect payment provider — a direct charge on the restaurant's own connected account.

"Direct" (not "destination") on purpose: ROADMAP decision D7 is that the restaurant is the merchant of
record, and Stripe's direct-charge model is what puts the charge, the statement descriptor, and the
dispute liability on *their* account rather than the platform's. `application_fee_amount` is how the
platform would take its own cut later — 0 until that's actually decided on.

The PaymentIntent confirms asynchronously: this only creates it and hands back its `client_secret` for
the frontend's Stripe.js to confirm (handles 3D Secure itself). The order is confirmed by the
`payment_intent.succeeded` webhook (`app/api/routes/webhooks.py`), never here — this class does not
touch the database at all.
"""

from decimal import Decimal

import stripe

from app.core.config import settings
from app.models.enums import PaymentStatus
from app.services.payments.base import IntentResult, PaymentProvider


def _minor_units(amount: Decimal, currency: str) -> int:
    # Stripe wants the smallest unit of the currency (cents for usd/gbp/eur). Zero-decimal currencies
    # (jpy, krw, ...) aren't handled here — not needed until a restaurant actually uses one.
    return int((amount * 100).to_integral_value())


class StripePaymentProvider(PaymentProvider):
    def __init__(self) -> None:
        # An instantiated client, not the deprecated global `stripe.api_key = ...` pattern.
        self.client = stripe.StripeClient(settings.STRIPE_SECRET_KEY)

    def create_intent(
        self,
        amount: Decimal,
        *,
        currency: str,
        connected_account_id: str | None,
        metadata: dict[str, str],
    ) -> IntentResult:
        if amount <= 0:
            return IntentResult(status=PaymentStatus.FAILED, failure_message="Invalid payment amount")
        if not connected_account_id:
            return IntentResult(
                status=PaymentStatus.FAILED,
                failure_message="This restaurant hasn't connected a Stripe account yet",
            )
        try:
            intent = self.client.v1.payment_intents.create(
                {
                    "amount": _minor_units(amount, currency),
                    "currency": currency,
                    "metadata": metadata,
                    "automatic_payment_methods": {"enabled": True},
                },
                # A direct charge: created *on* the restaurant's connected account (Stripe-Account
                # header), not the platform's — see this module's docstring.
                options={"stripe_account": connected_account_id},
            )
        except stripe.StripeError as exc:
            return IntentResult(status=PaymentStatus.FAILED, failure_message=str(exc.user_message or exc))
        return IntentResult(
            status=PaymentStatus.REQUIRES_ACTION,
            provider_intent_id=intent.id,
            client_secret=intent.client_secret,
        )
