"""Stripe Terminal setup that lives on the restaurant's connected account: the Location its readers register
to, and the Configuration that turns on on-reader tipping (the reader shows the tip screen itself, so the tip
lands inside the one card payment — see the webhook for how it's read back)."""

import logging

import stripe
from sqlalchemy.orm import Session
from stripe.params.terminal import (
    ConfigurationCreateParams,
    ConfigurationUpdateParams,
    LocationCreateParams,
    LocationCreateParamsAddress,
    LocationUpdateParams,
)

from app.core.config import settings
from app.core.exceptions import AppError, NotFoundError
from app.models.restaurant import Restaurant

logger = logging.getLogger(__name__)


class TerminalService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def sync_tipping(self, restaurant_id: int) -> dict[str, str | bool | None]:
        """Create/refresh the restaurant's Terminal location + tipping configuration from its tip settings."""
        restaurant = self.db.get(Restaurant, restaurant_id)
        if restaurant is None:
            raise NotFoundError("Restaurant not found")
        if settings.PAYMENT_PROVIDER.strip().lower() != "stripe":
            raise AppError("Card payments aren't set up for this platform yet")
        if not restaurant.stripe_account_id:
            raise AppError("Connect Stripe first — card readers belong to your own Stripe account")
        client = stripe.StripeClient(settings.STRIPE_SECRET_KEY)
        opts: stripe.RequestOptions = {"stripe_account": restaurant.stripe_account_id}
        try:
            location_id = restaurant.stripe_terminal_location_id or self._create_location(client, restaurant, opts)
            tipping = self._tipping(restaurant)
            if restaurant.stripe_terminal_config_id:
                update_params: ConfigurationUpdateParams = {"tipping": tipping} if tipping else {"tipping": ""}
                client.v1.terminal.configurations.update(restaurant.stripe_terminal_config_id, update_params, options=opts)
                config_id = restaurant.stripe_terminal_config_id
            else:
                create_params: ConfigurationCreateParams = {"name": f"{restaurant.name} tipping"}
                if tipping:
                    create_params["tipping"] = tipping
                config_id = client.v1.terminal.configurations.create(create_params, options=opts).id
            location_params: LocationUpdateParams = {"configuration_overrides": config_id}
            client.v1.terminal.locations.update(location_id, location_params, options=opts)
        except stripe.StripeError as exc:
            raise AppError(str(exc.user_message or exc)) from exc
        restaurant.stripe_terminal_location_id = location_id
        restaurant.stripe_terminal_config_id = config_id
        self.db.commit()
        return {"location_id": location_id, "configuration_id": config_id, "tipping": restaurant.tips_enabled}

    @staticmethod
    def _tipping(restaurant: Restaurant):
        if not restaurant.tips_enabled:
            return None
        presets = [int(p) for p in restaurant.tip_presets]
        # Stripe requires the same keys for every currency listed, so both of ours get the same shape.
        return {"usd": {"percentages": presets}, "cad": {"percentages": presets}}

    @staticmethod
    def _create_location(client: stripe.StripeClient, restaurant: Restaurant, opts: stripe.RequestOptions) -> str:
        address: LocationCreateParamsAddress = {
            "country": restaurant.country, "line1": restaurant.address or "Unknown",
            "city": restaurant.city or "", "postal_code": restaurant.postal_code or "",
        }
        if restaurant.state:
            address["state"] = restaurant.state
        params: LocationCreateParams = {"display_name": restaurant.name, "address": address}
        return client.v1.terminal.locations.create(params, options=opts).id
