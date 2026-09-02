"""Mock payment processing (replaceable with Stripe etc.)."""

import secrets
from decimal import Decimal

from app.models.enums import PaymentMethod, PaymentStatus


class PaymentResult:
    def __init__(
        self,
        *,
        success: bool,
        status: PaymentStatus,
        provider_reference: str | None = None,
        message: str | None = None,
    ) -> None:
        self.success = success
        self.status = status
        self.provider_reference = provider_reference
        self.message = message


class PaymentService:
    """Mock payment gateway — always succeeds for positive amounts."""

    def process(self, amount: Decimal, *, method: PaymentMethod = PaymentMethod.MOCK) -> PaymentResult:
        if amount <= 0:
            return PaymentResult(
                success=False,
                status=PaymentStatus.FAILED,
                message="Invalid payment amount",
            )
        reference = f"mock_{secrets.token_hex(8)}"
        return PaymentResult(
            success=True,
            status=PaymentStatus.COMPLETED,
            provider_reference=reference,
        )
