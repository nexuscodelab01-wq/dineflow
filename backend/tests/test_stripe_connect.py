"""Stripe Connect onboarding: the request shapes sent *to* Stripe (Accounts v2, not the deprecated v1
`type: 'express'` pattern), without a live network call. See test_webhooks.py for what happens once a
response comes back (the account.updated-equivalent v2 event)."""

from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AppError, NotFoundError
from app.models.restaurant import Restaurant
from app.services import stripe_connect_service as scs
from app.services.stripe_connect_service import StripeConnectService


class _FakeAccounts:
    def __init__(self) -> None:
        self.create_calls: list[dict] = []

    def create(self, params: dict):
        self.create_calls.append(params)
        return type("Account", (), {"id": "acct_fake_1"})()


class _FakeAccountLinks:
    def __init__(self) -> None:
        self.create_calls: list[dict] = []

    def create(self, params: dict):
        self.create_calls.append(params)
        return type("AccountLink", (), {"url": "https://connect.stripe.com/setup/fake"})()


class _FakeCore:
    def __init__(self) -> None:
        self.accounts = _FakeAccounts()
        self.account_links = _FakeAccountLinks()


class _FakeV2:
    def __init__(self) -> None:
        self.core = _FakeCore()


class _FakeStripeClient:
    """Stands in for stripe.StripeClient — captures what would have been sent, makes no network call."""

    last_instance: "_FakeStripeClient | None" = None

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        self.v2 = _FakeV2()
        _FakeStripeClient.last_instance = self


@pytest.fixture
def fake_stripe_client(monkeypatch):
    monkeypatch.setattr(scs.stripe, "StripeClient", _FakeStripeClient)
    monkeypatch.setattr(settings, "PAYMENT_PROVIDER", "stripe")
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_fake")
    monkeypatch.setattr(settings, "PUBLIC_SITE_URL", "http://localhost:3000")
    # Explicit rather than whatever happens to be in the environment: this is what makes site_url()
    # build a tenant-aware address ({slug}.{platform}) instead of falling back to the bare platform
    # domain — the exact bug (every restaurant's onboarding returning to the platform root instead of
    # its own site) that these return_url/refresh_url assertions exist to catch.
    monkeypatch.setattr(settings, "PLATFORM_DOMAIN", "dineflow.test")
    yield
    _FakeStripeClient.last_instance = None


def _restaurant(db: Session, **kwargs) -> Restaurant:
    r = Restaurant(name="Connect Test", slug="connect-test", tax_rate=Decimal("0.10"), delivery_fee=Decimal("2.00"), **kwargs)
    db.add(r)
    db.flush()
    return r


def test_refuses_to_onboard_when_payments_are_not_configured_for_stripe(db: Session, monkeypatch):
    monkeypatch.setattr(settings, "PAYMENT_PROVIDER", "mock")
    restaurant = _restaurant(db)
    with pytest.raises(AppError):
        StripeConnectService(db).onboarding_link(restaurant.id)


def test_onboarding_an_unknown_restaurant_is_a_clean_404(db: Session, fake_stripe_client):
    with pytest.raises(NotFoundError):
        StripeConnectService(db).onboarding_link(999999)


def test_creates_a_v2_full_dashboard_account_with_stripe_collecting_fees_and_losses(db: Session, fake_stripe_client):
    restaurant = _restaurant(db, email="owner@connect-test.demo")
    db.commit()

    url = StripeConnectService(db).onboarding_link(restaurant.id)

    assert url == "https://connect.stripe.com/setup/fake"
    created = _FakeStripeClient.last_instance.v2.core.accounts.create_calls[0]
    # Accounts v2 dimensions, never a v1 `type` — see this module's docstring.
    assert "type" not in created
    assert created["dashboard"] == "full"
    # Stripe rejects the merchant configuration outright without this — found in testing, not in docs.
    assert created["identity"] == {"country": "US"}
    assert created["configuration"]["merchant"]["capabilities"]["card_payments"]["requested"] is True
    assert created["defaults"] == {"responsibilities": {"fees_collector": "stripe", "losses_collector": "stripe"}}
    assert created["contact_email"] == "owner@connect-test.demo"

    db.refresh(restaurant)
    assert restaurant.stripe_account_id == "acct_fake_1"


def test_omits_contact_email_entirely_when_the_restaurant_has_none(db: Session, fake_stripe_client):
    restaurant = _restaurant(db, email=None)
    db.commit()

    StripeConnectService(db).onboarding_link(restaurant.id)

    created = _FakeStripeClient.last_instance.v2.core.accounts.create_calls[0]
    assert "contact_email" not in created


def test_reuses_the_existing_account_instead_of_creating_a_second_one(db: Session, fake_stripe_client):
    restaurant = _restaurant(db)
    restaurant.stripe_account_id = "acct_already_onboarding"
    db.commit()

    StripeConnectService(db).onboarding_link(restaurant.id)

    assert _FakeStripeClient.last_instance.v2.core.accounts.create_calls == []
    link_call = _FakeStripeClient.last_instance.v2.core.account_links.create_calls[0]
    assert link_call["account"] == "acct_already_onboarding"


def test_the_account_link_requests_up_front_collection_and_returns_to_this_restaurants_own_site(db: Session, fake_stripe_client):
    """Regression test: an earlier version sent every restaurant back to the bare platform domain
    (settings.PUBLIC_SITE_URL) instead of its own site — found by hand while testing evacakery."""
    restaurant = _restaurant(db)
    db.commit()

    StripeConnectService(db).onboarding_link(restaurant.id)

    link_call = _FakeStripeClient.last_instance.v2.core.account_links.create_calls[0]
    onboarding = link_call["use_case"]["account_onboarding"]
    assert onboarding["configurations"] == ["merchant"]
    assert onboarding["collection_options"] == {"fields": "eventually_due"}
    assert onboarding["return_url"] == "http://connect-test.dineflow.test:3000/admin/settings"
    assert onboarding["refresh_url"] == "http://connect-test.dineflow.test:3000/admin/settings"


def test_status_reflects_connected_and_charges_enabled(db: Session):
    restaurant = _restaurant(db)
    db.commit()
    assert StripeConnectService(db).status(restaurant.id) == {"connected": False, "charges_enabled": False}

    restaurant.stripe_account_id = "acct_x"
    restaurant.stripe_charges_enabled = True
    db.commit()
    assert StripeConnectService(db).status(restaurant.id) == {"connected": True, "charges_enabled": True}
