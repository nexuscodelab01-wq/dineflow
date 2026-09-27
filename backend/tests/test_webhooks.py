"""The Stripe webhook route: signature verification, the two payment outcomes, Connect status sync,
idempotency, and that one restaurant's event can never touch another's order (test_tenant_isolation.py's
route registry points here for that last one)."""

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


def test_account_updated_syncs_charges_enabled(client: TestClient, db: Session, monkeypatch):
    app.dependency_overrides[get_db] = override_get_db(db)
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", SECRET)
    restaurant = _restaurant(db, "webhook-connect")
    restaurant.stripe_account_id = "acct_test_1"
    db.commit()

    r = _post(client, _event("account.updated", {"id": "acct_test_1", "charges_enabled": True}))
    assert r.status_code == 200

    db.expire_all()
    assert db.get(Restaurant, restaurant.id).stripe_charges_enabled is True
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
