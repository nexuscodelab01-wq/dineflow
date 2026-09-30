"""The payment provider interface, and order creation against it."""

from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.main import app
from app.models.enums import PaymentMethod, PaymentStatus
from app.models.payment import Payment
from app.services.payments import get_payment_provider
from app.services.payments.mock_provider import MockPaymentProvider
from tests.conftest import override_get_db
from tests.tenants import header, make_tenant, place_order


def test_the_mock_provider_settles_instantly_and_refuses_a_non_positive_amount():
    provider = MockPaymentProvider()

    ok = provider.create_intent(Decimal("12.50"), currency="usd", connected_account_id=None, metadata={})
    assert ok.status == PaymentStatus.COMPLETED
    assert ok.provider_intent_id and ok.client_secret is None  # settles synchronously — nothing left to confirm

    bad = provider.create_intent(Decimal("0.00"), currency="usd", connected_account_id=None, metadata={})
    assert bad.status == PaymentStatus.FAILED and bad.failure_message


def test_the_mock_provider_can_refund_and_cancel():
    provider = MockPaymentProvider()

    refunded = provider.refund(provider_intent_id="mock_x", amount=Decimal("12.50"), currency="usd", connected_account_id=None)
    assert refunded.success and refunded.provider_reference

    cancelled = provider.cancel_intent(provider_intent_id="mock_x", connected_account_id=None)
    assert cancelled.success


def test_the_provider_factory_follows_the_payment_provider_setting(monkeypatch):
    monkeypatch.setattr(settings, "PAYMENT_PROVIDER", "mock")
    assert isinstance(get_payment_provider(), MockPaymentProvider)

    monkeypatch.setattr(settings, "PAYMENT_PROVIDER", "stripe")
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_x")
    from app.services.payments.stripe_provider import StripePaymentProvider

    assert isinstance(get_payment_provider(), StripePaymentProvider)


def test_placing_an_order_under_the_mock_provider_confirms_it_immediately_with_a_real_payment_row(client: TestClient, db: Session):
    app.dependency_overrides[get_db] = override_get_db(db)
    t = make_tenant(db, "Mockpay")

    r = place_order(client, t)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "CONFIRMED"
    # The mock provider settles synchronously, so there's nothing for a client to confirm.
    assert body.get("client_secret") is None

    payment = db.query(Payment).filter(Payment.order_id == body["id"]).one()
    assert payment.status == PaymentStatus.COMPLETED
    assert payment.payment_method == PaymentMethod.MOCK
    assert payment.provider == "MOCK"
    assert payment.restaurant_id == t.rid  # the audit's per-tenant payout-reconciliation gap, fixed
    assert payment.currency == "usd"

    app.dependency_overrides.clear()


def test_a_restaurant_not_connected_to_stripe_cannot_take_a_real_payment(client: TestClient, db: Session, monkeypatch):
    """Under PAYMENT_PROVIDER=stripe, an order for a restaurant with no stripe_account_id fails cleanly
    rather than silently charging nobody or crashing."""
    app.dependency_overrides[get_db] = override_get_db(db)
    t = make_tenant(db, "Nostripe")
    monkeypatch.setattr(settings, "PAYMENT_PROVIDER", "stripe")

    r = place_order(client, t)
    assert r.status_code == 400
    assert "connected a stripe account" in r.json()["detail"].lower()

    app.dependency_overrides.clear()
