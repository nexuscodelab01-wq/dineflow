from app.core.config import settings
from app.models.enums import PaymentStatus
from app.models.payment import Payment
from app.services.payments.base import IntentResult, PaymentProvider, RefundResult
from app.services.payments.mock_provider import MockPaymentProvider


def get_payment_provider() -> PaymentProvider:
    """The provider selected by `PAYMENT_PROVIDER` — "mock" (default; every test uses this) or "stripe"."""
    if settings.PAYMENT_PROVIDER.strip().lower() == "stripe":
        from app.services.payments.stripe_provider import StripePaymentProvider  # only import stripe if used

        return StripePaymentProvider()
    return MockPaymentProvider()


def reverse_payment(payment: Payment, *, connected_account_id: str | None) -> RefundResult:
    """The shared "undo" logic `OrderService.refund_payment` and `TableSessionService.refund_tab` both
    need — refunds a `COMPLETED` payment in full, or cancels one still `PENDING`/`REQUIRES_ACTION`
    (nothing was charged yet, but a stray later confirmation must not be allowed to charge a dead
    order/tab anyway). Mutates `payment`'s `status`/`failure_message` in place on success; the caller
    commits. Already-`FAILED`/`REFUNDED`, or nothing to reverse, is a no-op that reports success.

    Callers differ in what a *failed* reversal should do — see each one's own docstring — so this never
    raises itself, only reports what happened.
    """
    if payment.status == PaymentStatus.COMPLETED:
        if not payment.provider_intent_id:
            # A $0.00 payment (a coupon covered the whole order) — nothing was ever charged.
            payment.status = PaymentStatus.REFUNDED
            return RefundResult(success=True)
        result = get_payment_provider().refund(
            provider_intent_id=payment.provider_intent_id,
            amount=payment.amount,
            currency=payment.currency,
            connected_account_id=connected_account_id,
        )
        if result.success:
            payment.status = PaymentStatus.REFUNDED
        else:
            payment.failure_message = result.message
        return result

    if payment.status in (PaymentStatus.PENDING, PaymentStatus.REQUIRES_ACTION) and payment.provider_intent_id:
        result = get_payment_provider().cancel_intent(
            provider_intent_id=payment.provider_intent_id, connected_account_id=connected_account_id,
        )
        if result.success:
            payment.status = PaymentStatus.FAILED
            payment.failure_message = "Cancelled before payment completed"
        else:
            payment.failure_message = result.message
        return result

    return RefundResult(success=True)  # already FAILED/REFUNDED, or a PENDING payment with nothing to cancel


__all__ = ["IntentResult", "PaymentProvider", "RefundResult", "get_payment_provider", "reverse_payment"]
