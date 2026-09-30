"""The provider-agnostic payment interface.

Every payment gateway DineFlow might use — today's mock, Stripe, and later a kiosk/POS card terminal
(see ROADMAP §7.7) — implements this. `order_service.py` and the webhook route only ever talk to a
`PaymentProvider`, never to a specific SDK, so swapping or adding a provider never touches order logic.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal

from app.models.enums import PaymentStatus


@dataclass
class IntentResult:
    """What creating a charge attempt gives back, whichever provider handled it."""

    status: PaymentStatus
    provider_intent_id: str | None = None
    # Only set when the *client* still needs to do something (e.g. Stripe's Payment Element confirming
    # 3D Secure). None for a provider that settles synchronously, like the mock.
    client_secret: str | None = None
    failure_message: str | None = None


@dataclass
class RefundResult:
    success: bool
    provider_reference: str | None = None
    message: str | None = None


class PaymentProvider(ABC):
    @abstractmethod
    def create_intent(
        self,
        amount: Decimal,
        *,
        currency: str,
        connected_account_id: str | None,
        metadata: dict[str, str],
    ) -> IntentResult:
        """Start a charge attempt for `amount` (major units, e.g. 12.50 not 1250).

        `connected_account_id` is the restaurant's Stripe Connect account (or whatever the equivalent is
        for another provider); a provider that has no such concept ignores it.
        """

    @abstractmethod
    def refund(
        self, *, provider_intent_id: str, amount: Decimal, currency: str, connected_account_id: str | None
    ) -> RefundResult:
        """Refund a *completed* payment (in full — partial refunds aren't built yet)."""

    @abstractmethod
    def cancel_intent(self, *, provider_intent_id: str, connected_account_id: str | None) -> RefundResult:
        """Cancel a payment that hasn't completed yet (still PENDING/REQUIRES_ACTION) — nothing to refund
        since nothing was charged, but without this a stray later confirmation (e.g. a customer finishing
        a 3D Secure challenge after staff already cancelled the order) would still charge the card for an
        order that no longer exists."""
