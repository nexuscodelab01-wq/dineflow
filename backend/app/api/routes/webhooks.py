"""Stripe webhooks: how an asynchronous payment result reaches us.

No auth dependency here — Stripe can't hold a JWT. Trust comes from the signature instead
(`stripe.Webhook.construct_event`, checked against `STRIPE_WEBHOOK_SECRET`). The session runs in the
default bypass mode (no `enter_tenant_mode` call), same as `/tenant` and `/auth/login`, because a
webhook event names its own restaurant (via the payment/account it's about) rather than arriving with
one already established — see db/session.py's module docstring.

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
    except (ValueError, stripe.error.SignatureVerificationError):
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    handler = _HANDLERS.get(event["type"])
    if handler is not None:
        handler(db, event["data"]["object"])
    else:
        logger.info("Unhandled Stripe webhook event: %s", event["type"])
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
    last_error = intent.get("last_payment_error") or {}
    payment.failure_message = last_error.get("message") or "Payment failed"
    # The order itself stays PENDING — the customer can retry with a new payment intent.
    db.commit()


def _handle_account_updated(db: Session, account: dict) -> None:
    restaurant = db.scalar(select(Restaurant).where(Restaurant.stripe_account_id == account["id"]))
    if restaurant is None:
        return
    restaurant.stripe_charges_enabled = bool(account.get("charges_enabled"))
    db.commit()


_HANDLERS = {
    "payment_intent.succeeded": _handle_payment_succeeded,
    "payment_intent.payment_failed": _handle_payment_failed,
    "account.updated": _handle_account_updated,
}
