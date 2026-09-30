"""Stripe Connect onboarding: turning a restaurant into a connected account able to take payments.

Uses the **Accounts v2 API** (`/v2/core/accounts`), not the deprecated v1 `type: 'express'` pattern —
v2 configures three independent dimensions instead of a fixed account "type":
- `dashboard: "full"` — the restaurant manages its own Stripe account directly at dashboard.stripe.com.
  (`dashboard: "express"` paired with Stripe collecting fees/losses on a *direct* charge is a newer,
  public-preview combination not yet enabled on every platform account — it returned
  `InvalidRequestError: This account configuration is not supported` in testing. `"full"` is the
  plain, universally-supported way to get the same direct-charge SaaS model; worth revisiting once
  that preview is confirmed available, since a lightweight dashboard suits a small restaurant better.)
- `fees_collector: "stripe"` / `losses_collector: "stripe"` — Stripe bills the restaurant directly for
  card fees and is liable for negative balances, rather than DineFlow.
- `configuration.merchant.capabilities.card_payments` — required for a connected account to be a
  merchant of record and accept *direct* charges (see stripe_provider.py).

Separate from the payment providers in app/services/payments/ — those create *charges* against an
already-connected account; this is the one-time (or repeatable, if it lapses) setup that gets a
restaurant a `stripe_account_id` in the first place. Onboarding is Stripe-hosted (an Account Link), so
there is no custom KYC UI to build. `stripe_charges_enabled` is kept in sync by a webhook
(`v2.core.account[configuration.merchant].capability_status_updated`, see api/routes/webhooks.py) —
never read live from Stripe on a request, so a page load never depends on Stripe being reachable.
"""

import stripe
from sqlalchemy.orm import Session
from stripe.params.v2.core import AccountCreateParams

from app.core.config import settings
from app.core.exceptions import AppError, NotFoundError
from app.core.tenancy import site_url
from app.repositories.restaurant import RestaurantRepository


class StripeConnectService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.restaurants = RestaurantRepository(db)

    def _client(self) -> stripe.StripeClient:
        # A per-call instance, not the deprecated global `stripe.api_key = ...` pattern.
        return stripe.StripeClient(settings.STRIPE_SECRET_KEY)

    def _restaurant(self, restaurant_id: int):
        restaurant = self.restaurants.get_by_id(restaurant_id)
        if restaurant is None:
            raise NotFoundError("Restaurant not found")
        return restaurant

    def onboarding_link(self, restaurant_id: int) -> str:
        if settings.PAYMENT_PROVIDER.strip().lower() != "stripe":
            raise AppError("Payments aren't set up for this platform yet")

        client = self._client()
        restaurant = self._restaurant(restaurant_id)
        if not restaurant.stripe_account_id:
            account_params: AccountCreateParams = {
                "display_name": restaurant.name,
                "dashboard": "full",
                # Stripe requires identity.country before it will accept the merchant configuration (it
                # determines which regulatory requirements apply) — found the hard way, in testing.
                # DineFlow has no Restaurant.country field yet (only address/city/postal_code), so this
                # is hardcoded to the one country every demo/seed restaurant is in today. Add a real
                # Restaurant.country field and use it here before onboarding a restaurant outside the US.
                "identity": {"country": "US"},
                "configuration": {"merchant": {"capabilities": {"card_payments": {"requested": True}}}},
                "defaults": {"responsibilities": {"fees_collector": "stripe", "losses_collector": "stripe"}},
            }
            if restaurant.email:
                account_params["contact_email"] = restaurant.email
            account = client.v2.core.accounts.create(account_params)
            restaurant.stripe_account_id = account.id
            self.db.commit()

        # This restaurant's own address (evacakery.localhost:3000), not the bare platform domain —
        # a flat PUBLIC_SITE_URL here sent every restaurant back to the platform root instead of their
        # own site, found the hard way in testing.
        site = site_url(restaurant).rstrip("/")
        link = client.v2.core.account_links.create({
            "account": restaurant.stripe_account_id,
            "use_case": {
                "type": "account_onboarding",
                "account_onboarding": {
                    "configurations": ["merchant"],
                    # Up-front: collect everything Stripe will eventually need in one pass, rather than
                    # sending the restaurant back through onboarding again as they start earning more.
                    "collection_options": {"fields": "eventually_due"},
                    # A restaurant can restart onboarding from the same Settings page either way.
                    "refresh_url": f"{site}/admin/settings",
                    "return_url": f"{site}/admin/settings",
                },
            },
        })
        return link.url

    def status(self, restaurant_id: int) -> dict[str, bool]:
        restaurant = self._restaurant(restaurant_id)
        return {
            "connected": bool(restaurant.stripe_account_id),
            "charges_enabled": restaurant.stripe_charges_enabled,
        }
