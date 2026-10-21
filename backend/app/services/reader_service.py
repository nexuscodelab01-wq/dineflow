"""Server-driven Stripe Terminal readers (WisePOS E, S700): smart readers on the venue network that take the card
themselves. The till only says "charge this reader" — no Bluetooth pairing — and the result comes back through the
same payment webhooks as every other card payment."""

import logging

import stripe
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from stripe.params.terminal import ReaderCreateParams

from app.core.config import settings
from app.core.exceptions import AppError, NotFoundError
from app.models.enums import PaymentStatus
from app.models.order_item import OrderItem
from app.models.payment import Payment
from app.models.restaurant import Restaurant
from app.schemas.reader import ReaderRead
from app.services.payments import reverse_payment
from app.services.terminal_service import TerminalService

logger = logging.getLogger(__name__)


class ReaderService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def _restaurant(self, restaurant_id: int) -> Restaurant:
        restaurant = self.db.get(Restaurant, restaurant_id)
        if restaurant is None:
            raise NotFoundError("Restaurant not found")
        return restaurant

    @staticmethod
    def _live() -> bool:
        return settings.PAYMENT_PROVIDER.strip().lower() == "stripe"

    def _client(self) -> stripe.StripeClient:
        return stripe.StripeClient(settings.STRIPE_SECRET_KEY)

    def list_readers(self, restaurant_id: int) -> list[ReaderRead]:
        restaurant = self._restaurant(restaurant_id)
        if not self._live() or not restaurant.stripe_account_id or not restaurant.stripe_terminal_location_id:
            return []
        try:
            readers = self._client().v1.terminal.readers.list(
                {"location": restaurant.stripe_terminal_location_id, "limit": 20}, options={"stripe_account": restaurant.stripe_account_id},
            )
        except stripe.StripeError as exc:
            logger.warning("Could not list readers: %s", exc)
            return []
        return [ReaderRead(id=r.id, label=r.label or r.id, status=r.status or "unknown", device_type=r.device_type) for r in readers.data]

    def register(self, restaurant_id: int, registration_code: str, label: str) -> ReaderRead:
        restaurant = self._restaurant(restaurant_id)
        if not self._live():
            raise AppError("Card payments aren't set up for this platform yet")
        if not restaurant.stripe_account_id:
            raise AppError("Connect Stripe first — card readers belong to your own Stripe account")
        if not restaurant.stripe_terminal_location_id:
            TerminalService(self.db).sync_tipping(restaurant_id)  # creates the location (and the tipping configuration)
            self.db.refresh(restaurant)
        params: ReaderCreateParams = {"registration_code": registration_code.strip(), "label": label.strip(), "location": str(restaurant.stripe_terminal_location_id)}
        try:
            reader = self._client().v1.terminal.readers.create(params, options={"stripe_account": restaurant.stripe_account_id})
        except stripe.StripeError as exc:
            raise AppError(str(exc.user_message or exc)) from exc
        return ReaderRead(id=reader.id, label=reader.label or reader.id, status=reader.status or "unknown", device_type=reader.device_type)

    def remove(self, restaurant_id: int, reader_id: str) -> None:
        restaurant = self._restaurant(restaurant_id)
        self.require(restaurant_id, reader_id)
        try:
            self._client().v1.terminal.readers.delete(reader_id, options={"stripe_account": restaurant.stripe_account_id})
        except stripe.StripeError as exc:
            raise AppError(str(exc.user_message or exc)) from exc

    def require(self, restaurant_id: int, reader_id: str) -> None:
        """The reader must be one of THIS restaurant's — never trust an id the till sends."""
        if reader_id not in {r.id for r in self.list_readers(restaurant_id)}:
            raise NotFoundError("Card reader not found")

    def cancel(self, restaurant_id: int, staff_user_id: int, reader_id: str) -> None:
        """Stop what the reader is doing and fail this person's unfinished card payments, so the sale can be retried."""
        restaurant = self._restaurant(restaurant_id)
        self.require(restaurant_id, reader_id)
        try:
            self._client().v1.terminal.readers.cancel_action(reader_id, options={"stripe_account": restaurant.stripe_account_id})
        except stripe.StripeError as exc:
            logger.warning("cancel_action failed for %s: %s", reader_id, exc)
        for payment in self.db.scalars(select(Payment).where(
            Payment.restaurant_id == restaurant_id, Payment.staff_user_id == staff_user_id,
            Payment.status.in_((PaymentStatus.PENDING, PaymentStatus.REQUIRES_ACTION)), Payment.provider_intent_id.is_not(None),
        )):
            reverse_payment(payment, connected_account_id=restaurant.stripe_account_id)
            self.db.execute(update(OrderItem).where(OrderItem.paid_payment_id == payment.id).values(paid_payment_id=None))
        self.db.commit()
