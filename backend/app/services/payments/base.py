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

    def refund(self, *, provider_intent_id: str, amount: Decimal) -> RefundResult:
        """Refund all or part of a completed payment. Implemented in Sprint 4 Phase 2 — every provider
        raises until then, so a caller can't silently ship a refund button that does nothing."""
        raise NotImplementedError("Refunds land in Sprint 4 Phase 2")
