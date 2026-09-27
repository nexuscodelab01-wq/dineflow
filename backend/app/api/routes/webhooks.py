"""Stripe webhooks: how an asynchronous result reaches us.

No auth dependency here — Stripe can't hold a JWT. Trust comes from signature verification instead. The
session runs in the default bypass mode (no `enter_tenant_mode` call), same as `/tenant` and
`/auth/login`, because a webhook event names its own restaurant (via the payment/account it's about)
rather than arriving with one already established — see db/session.py's module docstring.

Two genuinely different Stripe subsystems land here, each with its own verification path and secret:
- **v1 classic events** (`payment_intent.*`) — fat payloads, verified with `stripe.Webhook.construct_event`
  and `STRIPE_WEBHOOK_SECRET`. Payments are still a v1 API; this is unaffected by the Connect v2 migration.
- **v2 core events** (Connect account status) — thin payloads (an id + a URL, not the object itself),
  verified with `client.parse_event_notification` and `STRIPE_CONNECT_WEBHOOK_SECRET` (a separate "event
  destination" resource from the v1 webhook endpoint, so it has its own signing secret), then fetched
  with `.fetch_related_object()` before use. See stripe_connect_service.py's docstring for why v2, not
  the deprecated v1 Connect API.

Stripe retries a webhook until it gets a 2xx, so every handler here is written to be safe to run twice.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.enums import OrderStatus, PaymentStatus
from app.models.order import Order
from app.models.payment import Payment
from app.models.restaurant import Restaurant
from app.services.order_service import OrderService

logger = logging.getLogger(__name__)
router = APIRouter()

_MERCHANT_CAPABILITY_STATUS_UPDATED = "v2.core.account[configuration.merchant].capability_status_updated"


@router.post("/webhooks/stripe", status_code=200)
async def stripe_webhook(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    stripe_signature: Annotated[str | None, Header(alias="Stripe-Signature")] = None,
) -> dict[str, bool]:
    import stripe  # imported lazily: the package is only needed when this route is actually hit

    if not settings.STRIPE_WEBHOOK_SECRET:
        # Not configured yet (PAYMENT_PROVIDER=mock, or Stripe keys not set up) — nothing to verify
        # against, so refuse rather than trust an unverified body.
        raise HTTPException(status_code=503, detail="Webhooks are not configured")

    payload = await request.body()
    try:
        event = stripe.Webhook.construct_event(payload, stripe_signature, settings.STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.SignatureVerificationError):
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    handler = _HANDLERS.get(event["type"])
    if handler is not None:
        handler(db, event["data"]["object"])
    else:
        logger.info("Unhandled Stripe webhook event: %s", event["type"])
    return {"received": True}


@router.post("/webhooks/stripe/connect", status_code=200)
async def stripe_connect_webhook(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    stripe_signature: Annotated[str | None, Header(alias="Stripe-Signature")] = None,
) -> dict[str, bool]:
    import stripe

    if not settings.STRIPE_CONNECT_WEBHOOK_SECRET:
        raise HTTPException(status_code=503, detail="Webhooks are not configured")

    payload = await request.body()
    client = stripe.StripeClient(settings.STRIPE_SECRET_KEY)
    try:
        notification = client.parse_event_notification(
            payload, stripe_signature, settings.STRIPE_CONNECT_WEBHOOK_SECRET
        )
    except stripe.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    if notification.type == _MERCHANT_CAPABILITY_STATUS_UPDATED:
        _handle_merchant_capability_status_updated(db, notification)
    else:
        logger.info("Unhandled Stripe Connect webhook event: %s", notification.type)
    return {"received": True}


def _handle_payment_succeeded(db: Session, intent: dict) -> None:
    payment = db.scalar(select(Payment).where(Payment.provider_intent_id == intent["id"]))
    if payment is None:
        logger.warning("payment_intent.succeeded for an unknown intent: %s", intent["id"])
        return
    order = db.get(Order, payment.order_id)
    if order is None or order.status != OrderStatus.PENDING:
        return  # already confirmed by an earlier delivery of this same event — nothing to do
    OrderService(db).confirm_payment(order, payment, user_id=None, notes="Payment confirmed (Stripe)")
    db.commit()
    logger.info("Order %s confirmed by webhook (intent %s)", order.order_number, intent["id"])


def _handle_payment_failed(db: Session, intent: dict) -> None:
    payment = db.scalar(select(Payment).where(Payment.provider_intent_id == intent["id"]))
    # A payment sits at REQUIRES_ACTION while Stripe.js is still working with the customer (3DS, a
    # retry after a decline, ...) — that's the state this event moves out of. Anything already
    # COMPLETED or FAILED is a replayed or out-of-order delivery; leave it alone.
    if payment is None or payment.status not in (PaymentStatus.PENDING, PaymentStatus.REQUIRES_ACTION):
        return
    payment.status = PaymentStatus.FAILED
    # `intent` is a StripeObject (from stripe.Webhook.construct_event), not a plain dict — it supports
    # `[]` but not `.get()`. `last_payment_error` may legitimately be absent (e.g. the intent expired
    # rather than a card declining), so `[]` alone isn't safe either — hence `.to_dict()` first.
    last_error = intent.to_dict().get("last_payment_error") or {}
    payment.failure_message = last_error.get("message") or "Payment failed"
    # The order itself stays PENDING — the customer can retry with a new payment intent.
    db.commit()


def _handle_merchant_capability_status_updated(db: Session, notification) -> None:
    """A v2 thin event carries only an id and a URL, not the account's current state (which capability
    changed is on the *full* Event, not this notification) — so the Account is always fetched fresh
    before we act on it (`fetch_related_object`, one API call) and every field re-synced from it."""
    account = notification.fetch_related_object()
    restaurant = db.scalar(select(Restaurant).where(Restaurant.stripe_account_id == account.id))
    if restaurant is None:
        return
    restaurant.stripe_charges_enabled = account.configuration.merchant.capabilities.card_payments.status == "active"
    db.commit()


_HANDLERS = {
    "payment_intent.succeeded": _handle_payment_succeeded,
    "payment_intent.payment_failed": _handle_payment_failed,
}
