"""Mock payment provider — always succeeds instantly for a positive amount.

This is the previous `PaymentService`, moved here unchanged so it implements `PaymentProvider`. It is
the default everywhere (`PAYMENT_PROVIDER=mock`) except a real production deployment, which
`assert_production_ready()` refuses to boot with this provider. Every automated test runs against it —
never against Stripe — which is what keeps order creation synchronous and testable without a network.
"""

import secrets
from decimal import Decimal

from app.models.enums import PaymentStatus
from app.services.payments.base import IntentResult, PaymentProvider


class MockPaymentProvider(PaymentProvider):
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
        return IntentResult(
            status=PaymentStatus.COMPLETED,
            provider_intent_id=f"mock_{secrets.token_hex(8)}",
        )

    # refund() is inherited from PaymentProvider (raises NotImplementedError) — lands in Phase 2.
