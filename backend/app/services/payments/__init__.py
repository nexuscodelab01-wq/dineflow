from app.core.config import settings
from app.services.payments.base import IntentResult, PaymentProvider, RefundResult
from app.services.payments.mock_provider import MockPaymentProvider


def get_payment_provider() -> PaymentProvider:
    """The provider selected by `PAYMENT_PROVIDER` — "mock" (default; every test uses this) or "stripe"."""
    if settings.PAYMENT_PROVIDER.strip().lower() == "stripe":
        from app.services.payments.stripe_provider import StripePaymentProvider  # only import stripe if used

        return StripePaymentProvider()
    return MockPaymentProvider()


__all__ = ["IntentResult", "PaymentProvider", "RefundResult", "get_payment_provider"]
