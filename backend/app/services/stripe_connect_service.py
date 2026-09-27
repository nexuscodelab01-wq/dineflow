"""Stripe Connect onboarding: turning a restaurant into a connected account able to take payments.

Separate from the payment providers in app/services/payments/ — those create *charges* against an
already-connected account; this is the one-time (or repeatable, if it lapses) setup that gets a
restaurant a `stripe_account_id` in the first place. Express accounts + Stripe-hosted Account Links, so
there is no custom KYC UI to build: the restaurant is redirected to Stripe, then back, and the
`account.updated` webhook (app/api/routes/webhooks.py) is what actually flips `stripe_charges_enabled`
— never read live from Stripe on a request, so a page load never depends on Stripe being reachable.
"""

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AppError, NotFoundError
from app.repositories.restaurant import RestaurantRepository


class StripeConnectService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.restaurants = RestaurantRepository(db)

    def _restaurant(self, restaurant_id: int):
        restaurant = self.restaurants.get_by_id(restaurant_id)
        if restaurant is None:
            raise NotFoundError("Restaurant not found")
        return restaurant

    def onboarding_link(self, restaurant_id: int) -> str:
        if settings.PAYMENT_PROVIDER.strip().lower() != "stripe":
            raise AppError("Payments aren't set up for this platform yet")
        import stripe  # imported lazily, same reasoning as app/services/payments/__init__.py

        stripe.api_key = settings.STRIPE_SECRET_KEY
        restaurant = self._restaurant(restaurant_id)
        if not restaurant.stripe_account_id:
            account = stripe.Account.create(type="express", email=restaurant.email or None)
            restaurant.stripe_account_id = account.id
            self.db.commit()
        site = settings.PUBLIC_SITE_URL.rstrip("/")
        link = stripe.AccountLink.create(
            account=restaurant.stripe_account_id,
            # A restaurant can restart onboarding from the same Settings page either way.
            refresh_url=f"{site}/admin/settings",
            return_url=f"{site}/admin/settings",
            type="account_onboarding",
        )
        return link.url

    def status(self, restaurant_id: int) -> dict[str, bool]:
        restaurant = self._restaurant(restaurant_id)
        return {
            "connected": bool(restaurant.stripe_account_id),
            "charges_enabled": restaurant.stripe_charges_enabled,
        }
