"""Tax behind the TaxCalculator seam: flat rate by default (parity with the old inline maths), Stripe Tax per
restaurant when the flag, a connected account and the mode are all on — with the flat rate as the fallback."""

from decimal import Decimal
from types import SimpleNamespace

import pytest
import stripe

from app.core.config import settings
from app.db.session import get_db
from app.main import app
from app.models.order import Order
from app.models.restaurant import Restaurant
from app.models.restaurant_user import RestaurantUser
from app.services.feature_service import FeatureService
from app.services.tax.base import TaxLine, TaxLocation, allocate
from app.services.tax.flat_provider import FlatTaxCalculator
from tests.conftest import override_get_db
from tests.tenants import header, make_tenant

API = "/api/v1"


class _Calculations:
    def __init__(self, owner):
        self.owner = owner

    def create(self, params, options=None):
        self.owner.calc_calls.append((params, options))
        if self.owner.fail:
            raise stripe.StripeError("boom")
        taxable = sum(i["amount"] for i in params["line_items"]) + params.get("shipping_cost", {}).get("amount", 0)
        tax = 0 if self.owner.rate is None else round(taxable * self.owner.rate)
        breakdown = [SimpleNamespace(taxability_reason="not_collecting" if self.owner.rate is None else "standard_rated")]
        return SimpleNamespace(id="taxcalc_1", tax_amount_exclusive=tax, tax_breakdown=breakdown)


class _Transactions:
    def __init__(self, owner):
        self.owner = owner

    def create_from_calculation(self, params, options=None):
        self.owner.tx_calls.append(params)
        return SimpleNamespace(id="tax_tx_1")

    def create_reversal(self, params, options=None):
        self.owner.reversals.append(params)
        return SimpleNamespace(id="tax_rev_1")


class FakeStripe:
    """Stands in for stripe.StripeClient: records calls, charges `rate` (None = not registered)."""

    rate: float | None = 0.07
    fail = False
    calc_calls: list = []
    tx_calls: list = []
    reversals: list = []

    def __init__(self, api_key):
        self.v1 = SimpleNamespace(tax=SimpleNamespace(calculations=_Calculations(FakeStripe), transactions=_Transactions(FakeStripe)))


@pytest.fixture(autouse=True)
def _reset_fake():
    FakeStripe.rate, FakeStripe.fail = 0.07, False
    FakeStripe.calc_calls, FakeStripe.tx_calls, FakeStripe.reversals = [], [], []


@pytest.fixture
def world(client, db):
    app.dependency_overrides[get_db] = override_get_db(db)
    a = make_tenant(db, "Alpha")
    FeatureService(db).set(a.rid, "pos", True, None, actor_label="test")
    yield type("W", (), {"client": client, "db": db, "a": a})
    app.dependency_overrides.clear()


@pytest.fixture
def stripe_tax(world, monkeypatch):
    """Alpha is on Stripe Tax: payment provider stripe (faked), account connected, flag + mode on."""
    monkeypatch.setattr(stripe, "StripeClient", FakeStripe)
    monkeypatch.setattr(settings, "PAYMENT_PROVIDER", "stripe")
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_fake")
    w = world
    r = w.db.get(Restaurant, w.a.rid)
    r.stripe_account_id, r.tax_mode, r.state, r.address, r.city, r.postal_code = "acct_x", "STRIPE", "WA", "1 Pike St", "Seattle", "98101"
    FeatureService(w.db).set(w.a.rid, "stripe_tax", True, None, actor_label="test")
    w.db.commit()
    return w


def pos_headers(w, pin="1234"):
    mid = w.db.query(RestaurantUser).filter_by(restaurant_id=w.a.rid, user_id=w.a.staff.id).one().id
    w.client.post(f"{API}/admin/devices/staff/{mid}/pin", params={"restaurant_id": w.a.rid}, headers=header(w.a.admin), json={"pin": pin})
    token = w.client.post(f"{API}/admin/devices", params={"restaurant_id": w.a.rid}, headers=header(w.a.admin), json={"label": "Till"}).json()["device_token"]
    login = w.client.post(f"{API}/pos/auth/pin-login", headers={"Authorization": f"Bearer {token}"}, json={"pin": pin}).json()
    return {"Authorization": f"Bearer {login['pos_session_token']}"}


def counter_order(w, headers, qty=1):
    r = w.client.post(f"{API}/pos/orders", headers=headers, json={"items": [{"menu_item_id": w.a.item.id, "quantity": qty, "modifier_option_ids": []}]})
    assert r.status_code == 201, r.text
    return r.json()


# ---------------------------------------------------------------- the seam

def test_flat_calculator_matches_the_old_inline_maths():
    q = FlatTaxCalculator(Decimal("0.10")).quote(
        [TaxLine("a", Decimal("12.00")), TaxLine("b", Decimal("7.33"))], location=TaxLocation(country="US"), shipping=Decimal("2.00"), currency="usd",
    )
    assert q.tax_total == Decimal("1.93")  # 19.33 × 10%, delivery fee untaxed, as before
    assert sum(q.line_tax.values()) == q.tax_total


def test_allocate_always_sums_exactly():
    parts = allocate(Decimal("0.10"), [Decimal("1"), Decimal("1"), Decimal("1")])
    assert sum(parts) == Decimal("0.10")


def test_flat_is_the_default_so_existing_restaurants_are_unchanged(world):
    body = counter_order(world, pos_headers(world))
    assert body["total"] == "13.20"  # 12.00 + 10%
    assert FakeStripe.calc_calls == []


# ---------------------------------------------------------------- stripe tax

def test_a_stripe_tax_restaurant_gets_stripes_number_and_the_address_it_sent(stripe_tax):
    w = stripe_tax
    body = counter_order(w, pos_headers(w))
    assert body["total"] == "12.84"  # 12.00 + 7% from Stripe, not the flat 10%
    params, options = FakeStripe.calc_calls[0]
    assert options == {"stripe_account": "acct_x"}
    assert params["customer_details"]["address"] == {"country": "US", "state": "WA", "postal_code": "98101", "city": "Seattle", "line1": "1 Pike St"}
    assert params["line_items"][0]["tax_code"] == "txcd_40060003"  # the restaurant's default
    order = w.db.get(Order, body["order_id"])
    assert order.tax_calculation_id == "taxcalc_1"
    assert order.items[0].tax_amount == Decimal("0.84")


def test_an_items_own_tax_code_wins_over_the_default(stripe_tax):
    w = stripe_tax
    w.a.item.tax_code = "txcd_41020001"
    w.db.commit()
    counter_order(w, pos_headers(w))
    assert FakeStripe.calc_calls[0][0]["line_items"][0]["tax_code"] == "txcd_41020001"


def test_a_stripe_outage_falls_back_to_the_flat_rate(stripe_tax):
    FakeStripe.fail = True
    body = counter_order(stripe_tax, pos_headers(stripe_tax))
    assert body["total"] == "13.20"


def test_stripe_mode_is_ignored_when_the_flag_is_off(stripe_tax):
    FeatureService(stripe_tax.db).set(stripe_tax.a.rid, "stripe_tax", False, None, actor_label="test")
    stripe_tax.db.commit()
    assert counter_order(stripe_tax, pos_headers(stripe_tax))["total"] == "13.20"
    assert FakeStripe.calc_calls == []


def test_delivery_is_taxed_at_the_delivery_address_and_shipping_is_included(stripe_tax):
    w = stripe_tax
    r = w.client.post(f"{API}/orders/quote", headers=header(w.a.customer), json={
        "restaurant_id": w.a.rid, "order_type": "DELIVERY",
        "items": [{"menu_item_id": w.a.item.id, "quantity": 1, "modifier_option_ids": []}],
        "delivery_address": {"street": "9 Elm", "city": "Tacoma", "postal_code": "98402", "state": "wa"},
    })
    assert r.status_code == 200, r.text
    params, _ = FakeStripe.calc_calls[0]
    assert params["customer_details"]["address"]["city"] == "Tacoma"
    assert params["shipping_cost"]["amount"] == 200
    assert Decimal(r.json()["tax"]) == Decimal("0.98")  # 7% of 12.00 + 2.00
    assert w.db.query(Order).filter_by(restaurant_id=w.a.rid).count() == 0  # a quote saves nothing


def test_pickup_quote_uses_the_restaurants_own_address(stripe_tax):
    w = stripe_tax
    r = w.client.post(f"{API}/orders/quote", headers=header(w.a.customer), json={
        "restaurant_id": w.a.rid, "order_type": "PICKUP", "items": [{"menu_item_id": w.a.item.id, "quantity": 2, "modifier_option_ids": []}],
    })
    assert r.status_code == 200, r.text
    assert FakeStripe.calc_calls[0][0]["customer_details"]["address"]["city"] == "Seattle"
    assert r.json()["subtotal"] == "24.00" and r.json()["tax"] == "1.68" and r.json()["total"] == "25.68"


def test_a_quote_matches_the_flat_maths_for_a_flat_restaurant(world):
    r = world.client.post(f"{API}/orders/quote", headers=header(world.a.customer), json={
        "restaurant_id": world.a.rid, "order_type": "PICKUP", "items": [{"menu_item_id": world.a.item.id, "quantity": 1, "modifier_option_ids": []}],
    })
    assert r.json() == {"subtotal": "12.00", "discount": "0.00", "tax": "1.20", "delivery_fee": "0.00", "total": "13.20"}


def test_a_paid_sale_is_recorded_once_and_a_refund_reverses_it(stripe_tax):
    w = stripe_tax
    headers = pos_headers(w)
    body = counter_order(w, headers)
    assert w.client.post(f"{API}/pos/orders/{body['order_id']}/pay-cash", headers=headers).status_code == 204
    order = w.db.get(Order, body["order_id"])
    assert FakeStripe.tx_calls == [{"calculation": "taxcalc_1", "reference": order.order_number}]
    assert order.tax_transaction_id == "tax_tx_1"

    from app.models.payment import Payment
    from app.services.order_service import OrderService

    OrderService(w.db).refund_payment(order, w.db.query(Payment).filter_by(order_id=order.id).one(), user_id=None)
    assert FakeStripe.reversals == [{"mode": "full", "original_transaction": "tax_tx_1", "reference": f"{order.order_number}-refund"}]


# ---------------------------------------------------------------- settings

def settings_patch(w, **body):
    return w.client.patch(f"{API}/admin/settings", params={"restaurant_id": w.a.rid}, headers=header(w.a.admin), json=body)


def test_stripe_mode_needs_a_connected_account_and_the_flag(world):
    assert settings_patch(world, tax_mode="STRIPE").status_code == 400  # not connected
    world.db.get(Restaurant, world.a.rid).stripe_account_id = "acct_x"
    world.db.commit()
    assert settings_patch(world, tax_mode="STRIPE").status_code == 400  # flag off
    FeatureService(world.db).set(world.a.rid, "stripe_tax", True, None, actor_label="test")
    assert settings_patch(world, tax_mode="STRIPE", state="wa").json()["state"] == "WA"


def test_unknown_tax_codes_are_refused(world):
    assert settings_patch(world, default_tax_code="txcd_nope").status_code == 422


def test_tax_check_reports_a_missing_registration(stripe_tax):
    FakeStripe.rate = None
    r = stripe_tax.client.post(f"{API}/admin/settings/tax-check", params={"restaurant_id": stripe_tax.a.rid}, headers=header(stripe_tax.a.admin))
    assert r.status_code == 200
    assert r.json()["ok"] is False and "registration" in r.json()["message"]


def test_tax_check_reports_the_rate_when_working(stripe_tax):
    r = stripe_tax.client.post(f"{API}/admin/settings/tax-check", params={"restaurant_id": stripe_tax.a.rid}, headers=header(stripe_tax.a.admin)).json()
    assert r["ok"] is True and Decimal(r["rate_percent"]) == Decimal("7.000")
