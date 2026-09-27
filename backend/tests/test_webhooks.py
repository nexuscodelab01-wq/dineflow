"""The Stripe webhook routes: signature verification, the two payment outcomes (v1), Connect account
status sync (v2 — see stripe_connect_service.py for why v2, and webhooks.py's docstring for how its
verification differs from v1's), idempotency, and that one restaurant's event can never touch another's
order (test_tenant_isolation.py's route registry points here for that last one)."""

import hashlib
import hmac
import json
import time
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.main import app
from app.models.enums import OrderStatus, OrderType, PaymentMethod, PaymentStatus
from app.models.order import Order
from app.models.order_status_history import OrderStatusHistory
from app.models.payment import Payment
from app.models.restaurant import Restaurant
from app.models.restaurant_table import RestaurantTable
from app.models.table_session import CLOSED
from app.models.table_session import OPEN as SESSION_OPEN
from app.models.table_session import TableSession
from tests.conftest import override_get_db

SECRET = "whsec_test_secret"


def _sign(payload: bytes, secret: str = SECRET) -> str:
    """Reproduces Stripe's documented webhook signature scheme exactly (what stripe.Webhook.construct_event
    verifies against) — no dependency on any stripe-python test helper or internal API."""
    timestamp = str(int(time.time()))
    signed_payload = f"{timestamp}.{payload.decode()}".encode()
    digest = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={digest}"


def _event(event_type: str, obj: dict) -> bytes:
    return json.dumps({"id": "evt_test", "type": event_type, "data": {"object": obj}}).encode()


def _pending_order_awaiting_stripe(db: Session, restaurant: Restaurant, *, intent_id: str) -> tuple[Order, Payment]:
    """An order exactly as `order_service.create_order` leaves one under a real (non-mock) provider:
    PENDING, with a REQUIRES_ACTION payment holding the PaymentIntent id a webhook will look it up by."""
    order = Order(
        restaurant_id=restaurant.id,
        order_number=f"WH-{intent_id}",
        order_type=OrderType.PICKUP,
        status=OrderStatus.PENDING,
        subtotal=Decimal("20.00"), tax=Decimal("2.00"), delivery_fee=Decimal("0.00"), discount=Decimal("0.00"),
        total=Decimal("22.00"),
        customer_name="Webhook Test",
        customer_email="webhook-test@demo.com",
    )
    db.add(order)
    db.flush()
    db.add(OrderStatusHistory(order_id=order.id, previous_status=None, new_status=OrderStatus.PENDING, changed_by_user_id=None))
    payment = Payment(
        order_id=order.id, restaurant_id=restaurant.id, amount=order.total, currency="usd",
        status=PaymentStatus.REQUIRES_ACTION, payment_method=PaymentMethod.CARD, provider="STRIPE",
        provider_intent_id=intent_id,
    )
    db.add(payment)
    db.flush()
    db.expire_all()
    return order, payment


def _pending_table_session_awaiting_stripe(db: Session, restaurant: Restaurant, *, intent_id: str) -> tuple[TableSession, Payment]:
    """A table session with a real payment mid-flight — the shape TableSessionService.pay() leaves one
    in under a real (non-mock) provider."""
    table = RestaurantTable(restaurant_id=restaurant.id, table_number=f"WH-{intent_id}", capacity=2)
    db.add(table)
    db.flush()
    session = TableSession(restaurant_id=restaurant.id, table_id=table.id, state=SESSION_OPEN)
    db.add(session)
    db.flush()
    payment = Payment(
        table_session_id=session.id, order_id=None, restaurant_id=restaurant.id, amount=Decimal("22.00"),
        currency="usd", status=PaymentStatus.REQUIRES_ACTION, payment_method=PaymentMethod.CARD,
        provider="STRIPE", provider_intent_id=intent_id,
    )
    db.add(payment)
    db.flush()
    db.expire_all()
    return session, payment


def _restaurant(db: Session, slug: str) -> Restaurant:
    r = Restaurant(name=slug, slug=slug, tax_rate=Decimal("0.10"), delivery_fee=Decimal("2.00"))
    db.add(r)
    db.flush()
    return r


def _post(client: TestClient, payload: bytes, *, secret: str = SECRET) -> object:
    return client.post("/api/v1/webhooks/stripe", content=payload, headers={"Stripe-Signature": _sign(payload, secret)})


def test_refuses_a_request_with_no_signing_secret_configured(client: TestClient, db: Session, monkeypatch):
    app.dependency_overrides[get_db] = override_get_db(db)
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", "")
    r = _post(client, _event("payment_intent.succeeded", {"id": "pi_x"}))
    assert r.status_code == 503
    app.dependency_overrides.clear()


def test_refuses_a_bad_or_missing_signature(client: TestClient, db: Session, monkeypatch):
    app.dependency_overrides[get_db] = override_get_db(db)
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", SECRET)
    payload = _event("payment_intent.succeeded", {"id": "pi_x"})

    wrong_secret = _post(client, payload, secret="whsec_someone_elses")
    assert wrong_secret.status_code == 400

    no_header = client.post("/api/v1/webhooks/stripe", content=payload)
    assert no_header.status_code == 400
    app.dependency_overrides.clear()


def test_payment_succeeded_confirms_the_order_exactly_once(client: TestClient, db: Session, monkeypatch):
    app.dependency_overrides[get_db] = override_get_db(db)
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", SECRET)
    restaurant = _restaurant(db, "webhook-success")
    order, payment = _pending_order_awaiting_stripe(db, restaurant, intent_id="pi_succeed_1")
    db.commit()

    r = _post(client, _event("payment_intent.succeeded", {"id": "pi_succeed_1"}))
    assert r.status_code == 200

    db.expire_all()
    refreshed_order = db.get(Order, order.id)
    refreshed_payment = db.get(Payment, payment.id)
    assert refreshed_order.status == OrderStatus.CONFIRMED
    assert refreshed_payment.status == PaymentStatus.COMPLETED
    history = db.query(OrderStatusHistory).filter(OrderStatusHistory.order_id == order.id).all()
    assert [h.new_status for h in history] == [OrderStatus.PENDING, OrderStatus.CONFIRMED]

    # Stripe retries until it gets a 2xx — replaying the same event must not re-confirm or duplicate anything.
    replay = _post(client, _event("payment_intent.succeeded", {"id": "pi_succeed_1"}))
    assert replay.status_code == 200
    db.expire_all()
    history_after_replay = db.query(OrderStatusHistory).filter(OrderStatusHistory.order_id == order.id).all()
    assert len(history_after_replay) == 2  # unchanged
    app.dependency_overrides.clear()


def test_payment_failed_marks_the_payment_and_leaves_the_order_pending_for_a_retry(client: TestClient, db: Session, monkeypatch):
    app.dependency_overrides[get_db] = override_get_db(db)
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", SECRET)
    restaurant = _restaurant(db, "webhook-decline")
    order, payment = _pending_order_awaiting_stripe(db, restaurant, intent_id="pi_decline_1")
    db.commit()

    r = _post(client, _event("payment_intent.payment_failed", {
        "id": "pi_decline_1", "last_payment_error": {"message": "Your card was declined."},
    }))
    assert r.status_code == 200

    db.expire_all()
    assert db.get(Order, order.id).status == OrderStatus.PENDING
    refreshed_payment = db.get(Payment, payment.id)
    assert refreshed_payment.status == PaymentStatus.FAILED
    assert refreshed_payment.failure_message == "Your card was declined."
    app.dependency_overrides.clear()


def test_payment_succeeded_settles_a_table_session_payment_and_closes_the_tab(client: TestClient, db: Session, monkeypatch):
    """The pay-at-table equivalent of test_payment_succeeded_confirms_the_order_exactly_once — no single
    order to confirm here, since every round on the tab is already CONFIRMED; settling means closing."""
    app.dependency_overrides[get_db] = override_get_db(db)
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", SECRET)
    restaurant = _restaurant(db, "webhook-table-pay")
    session, payment = _pending_table_session_awaiting_stripe(db, restaurant, intent_id="pi_table_1")
    db.commit()

    r = _post(client, _event("payment_intent.succeeded", {"id": "pi_table_1"}))
    assert r.status_code == 200

    db.expire_all()
    assert db.get(TableSession, session.id).state == CLOSED
    assert db.get(Payment, payment.id).status == PaymentStatus.COMPLETED

    # Replayed delivery: the session is already closed, so this must be a no-op, not an error.
    replay = _post(client, _event("payment_intent.succeeded", {"id": "pi_table_1"}))
    assert replay.status_code == 200
    app.dependency_overrides.clear()


def _connect_post(client: TestClient, payload: bytes, *, secret: str = SECRET) -> object:
    return client.post(
        "/api/v1/webhooks/stripe/connect", content=payload, headers={"Stripe-Signature": _sign(payload, secret)}
    )


def _connect_event(account_id: str) -> bytes:
    """A v2 *thin* event — an id and a URL, not the account's data (see webhooks.py's docstring: the
    handler always fetches the current account rather than trusting anything in the payload itself)."""
    return json.dumps({
        "id": "evt_test_v2",
        "object": "v2.core.event",
        "type": "v2.core.account[configuration.merchant].capability_status_updated",
        "created": "2026-01-01T00:00:00Z",
        "related_object": {"id": account_id, "type": "v2.core.account", "url": f"/v2/core/accounts/{account_id}"},
    }).encode()


class _FakeCardPayments:
    def __init__(self, status: str) -> None:
        self.status = status


class _FakeMerchantCapabilities:
    def __init__(self, status: str) -> None:
        self.card_payments = _FakeCardPayments(status)


class _FakeMerchantConfig:
    def __init__(self, status: str) -> None:
        self.capabilities = _FakeMerchantCapabilities(status)


class _FakeConfiguration:
    def __init__(self, status: str) -> None:
        self.merchant = _FakeMerchantConfig(status)


class _FakeAccount:
    """Stands in for the real Account v2 object `fetch_related_object()` would return — a live call to
    Stripe is exactly what these tests must not depend on. See test_stripe_connect.py for the request
    shapes sent *to* Stripe; this is about what happens once a response comes back."""

    def __init__(self, account_id: str, *, card_payments_status: str) -> None:
        self.id = account_id
        self.configuration = _FakeConfiguration(card_payments_status)


def _stub_fetch_related_object(monkeypatch, account: "_FakeAccount") -> None:
    from stripe.events._v2_core_account_including_configuration_merchant_capability_status_updated_event import (
        V2CoreAccountIncludingConfigurationMerchantCapabilityStatusUpdatedEventNotification,
    )

    monkeypatch.setattr(
        V2CoreAccountIncludingConfigurationMerchantCapabilityStatusUpdatedEventNotification,
        "fetch_related_object",
        lambda self: account,
    )


def test_connect_webhook_refuses_a_request_with_no_signing_secret_configured(client: TestClient, db: Session, monkeypatch):
    app.dependency_overrides[get_db] = override_get_db(db)
    monkeypatch.setattr(settings, "STRIPE_CONNECT_WEBHOOK_SECRET", "")
    r = _connect_post(client, _connect_event("acct_x"))
    assert r.status_code == 503
    app.dependency_overrides.clear()


def test_connect_webhook_refuses_a_bad_signature(client: TestClient, db: Session, monkeypatch):
    app.dependency_overrides[get_db] = override_get_db(db)
    monkeypatch.setattr(settings, "STRIPE_CONNECT_WEBHOOK_SECRET", SECRET)
    r = _connect_post(client, _connect_event("acct_x"), secret="whsec_someone_elses")
    assert r.status_code == 400
    app.dependency_overrides.clear()


def test_connect_webhook_syncs_charges_enabled_once_card_payments_is_active(client: TestClient, db: Session, monkeypatch):
    app.dependency_overrides[get_db] = override_get_db(db)
    monkeypatch.setattr(settings, "STRIPE_CONNECT_WEBHOOK_SECRET", SECRET)
    restaurant = _restaurant(db, "webhook-connect")
    restaurant.stripe_account_id = "acct_test_1"
    db.commit()
    _stub_fetch_related_object(monkeypatch, _FakeAccount("acct_test_1", card_payments_status="active"))

    r = _connect_post(client, _connect_event("acct_test_1"))
    assert r.status_code == 200

    db.expire_all()
    assert db.get(Restaurant, restaurant.id).stripe_charges_enabled is True
    app.dependency_overrides.clear()


def test_connect_webhook_can_also_turn_charges_enabled_back_off(client: TestClient, db: Session, monkeypatch):
    """A capability can regress (e.g. Stripe needs new information) — the sync must not be one-directional."""
    app.dependency_overrides[get_db] = override_get_db(db)
    monkeypatch.setattr(settings, "STRIPE_CONNECT_WEBHOOK_SECRET", SECRET)
    restaurant = _restaurant(db, "webhook-connect-regress")
    restaurant.stripe_account_id = "acct_test_2"
    restaurant.stripe_charges_enabled = True
    db.commit()
    _stub_fetch_related_object(monkeypatch, _FakeAccount("acct_test_2", card_payments_status="pending"))

    r = _connect_post(client, _connect_event("acct_test_2"))
    assert r.status_code == 200

    db.expire_all()
    assert db.get(Restaurant, restaurant.id).stripe_charges_enabled is False
    app.dependency_overrides.clear()


def test_connect_webhook_for_an_unknown_account_is_a_harmless_no_op(client: TestClient, db: Session, monkeypatch):
    app.dependency_overrides[get_db] = override_get_db(db)
    monkeypatch.setattr(settings, "STRIPE_CONNECT_WEBHOOK_SECRET", SECRET)
    _stub_fetch_related_object(monkeypatch, _FakeAccount("acct_nobody", card_payments_status="active"))

    r = _connect_post(client, _connect_event("acct_nobody"))
    assert r.status_code == 200
    app.dependency_overrides.clear()


def test_an_events_intent_id_can_only_ever_match_its_own_orders_payment(client: TestClient, db: Session, monkeypatch):
    """Not a real cross-tenant attack (nothing here is keyed by a tenant claim to begin with — the
    lookup is by the globally-unique provider_intent_id) — this documents *why* that's still safe, for
    test_tenant_isolation.py's route registry."""
    app.dependency_overrides[get_db] = override_get_db(db)
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", SECRET)
    a, b = _restaurant(db, "webhook-a"), _restaurant(db, "webhook-b")
    order_a, _ = _pending_order_awaiting_stripe(db, a, intent_id="pi_a_only")
    order_b, _ = _pending_order_awaiting_stripe(db, b, intent_id="pi_b_only")
    db.commit()

    _post(client, _event("payment_intent.succeeded", {"id": "pi_a_only"}))

    db.expire_all()
    assert db.get(Order, order_a.id).status == OrderStatus.CONFIRMED
    assert db.get(Order, order_b.id).status == OrderStatus.PENDING  # untouched
    app.dependency_overrides.clear()


def test_an_unhandled_event_type_is_acknowledged_without_error(client: TestClient, db: Session, monkeypatch):
    app.dependency_overrides[get_db] = override_get_db(db)
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", SECRET)
    r = _post(client, _event("charge.dispute.created", {"id": "dp_1"}))
    assert r.status_code == 200
    app.dependency_overrides.clear()
