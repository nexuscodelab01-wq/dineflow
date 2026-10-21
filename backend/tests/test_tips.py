"""Tips + service charge: the tip read back from Stripe, cash tips and cash-up, pooling, the finalized ledger."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
import stripe

from app.api.routes.webhooks import _handle_payment_succeeded
from app.core.config import settings
from app.db.session import get_db
from app.main import app
from app.models.enums import OrderStatus, PaymentMethod, PaymentStatus
from app.models.order import Order
from app.models.payment import Payment
from app.models.restaurant import Restaurant
from app.models.restaurant_user import RestaurantUser
from app.models.time_entry import TimeEntry
from app.services.feature_service import FeatureService
from tests.conftest import override_get_db
from tests.tenants import header, make_tenant

API = "/api/v1"


@pytest.fixture
def world(client, db):
    app.dependency_overrides[get_db] = override_get_db(db)
    a = make_tenant(db, "Alpha")
    FeatureService(db).set(a.rid, "pos", True, None, actor_label="test")
    FeatureService(db).set(a.rid, "tips", True, None, actor_label="test")
    yield type("W", (), {"client": client, "db": db, "a": a})
    app.dependency_overrides.clear()


def pos_headers(w, user=None, pin="1234", device_token=None):
    user = user or w.a.staff
    mid = w.db.query(RestaurantUser).filter_by(restaurant_id=w.a.rid, user_id=user.id).one().id
    w.client.post(f"{API}/admin/devices/staff/{mid}/pin", params={"restaurant_id": w.a.rid}, headers=header(w.a.admin), json={"pin": pin})
    token = device_token or w.client.post(f"{API}/admin/devices", params={"restaurant_id": w.a.rid}, headers=header(w.a.admin), json={"label": "Till"}).json()["device_token"]
    login = w.client.post(f"{API}/pos/auth/pin-login", headers={"Authorization": f"Bearer {token}"}, json={"pin": pin}).json()
    return {"Authorization": f"Bearer {login['pos_session_token']}"}, login


def settings_patch(w, **body):
    return w.client.patch(f"{API}/admin/settings", params={"restaurant_id": w.a.rid}, headers=header(w.a.admin), json=body)


def counter_order(w, headers):
    r = w.client.post(f"{API}/pos/orders", headers=headers, json={"items": [{"menu_item_id": w.a.item.id, "quantity": 1, "modifier_option_ids": []}]})
    assert r.status_code == 201, r.text
    return r.json()


# ---------------------------------------------------------------- service charge

def test_service_charge_is_its_own_line_and_untaxed_by_default(world):
    assert settings_patch(world, service_charge_rate="0.10", service_charge_order_types=["COUNTER"]).status_code == 200
    headers, _ = pos_headers(world)
    body = counter_order(world, headers)
    assert body["total"] == "14.40"  # 12.00 + 10% tax + 10% service charge
    assert world.db.get(Order, body["order_id"]).service_charge == Decimal("1.20")


def test_a_taxable_service_charge_is_in_the_tax_base(world):
    settings_patch(world, service_charge_rate="0.10", service_charge_order_types=["COUNTER"], service_charge_taxable=True)
    headers, _ = pos_headers(world)
    assert counter_order(world, headers)["total"] == "14.52"  # tax on 13.20


def test_service_charge_only_applies_to_the_chosen_order_types(world):
    settings_patch(world, service_charge_rate="0.10", service_charge_order_types=["DINE_IN"])
    headers, _ = pos_headers(world)
    assert counter_order(world, headers)["total"] == "13.20"


def test_tips_and_service_charge_need_the_flag(world):
    FeatureService(world.db).set(world.a.rid, "tips", False, None, actor_label="test")
    world.db.commit()
    assert settings_patch(world, tips_enabled=True).status_code == 400
    assert settings_patch(world, service_charge_rate="0.1").status_code == 400
    assert settings_patch(world, tip_presets=[10, 15]).status_code == 422


def test_pin_login_tells_the_app_whether_tips_are_on(world):
    settings_patch(world, tips_enabled=True)
    _, login = pos_headers(world)
    assert login["tips_enabled"] is True


# ---------------------------------------------------------------- the tip comes back from Stripe

def test_the_webhook_records_the_on_reader_tip_separately(world):
    w = world
    headers, _ = pos_headers(w)
    body = counter_order(w, headers)
    order = w.db.get(Order, body["order_id"])
    payment = Payment(
        order_id=order.id, restaurant_id=w.a.rid, amount=order.total, currency="usd", payment_method=PaymentMethod.CARD,
        provider="STRIPE", provider_intent_id="pi_tip", status=PaymentStatus.PENDING, staff_user_id=w.a.staff.id,
    )
    w.db.add(payment)
    w.db.commit()
    intent = stripe.StripeObject.construct_from({"id": "pi_tip", "amount_details": {"tip": {"amount": 250}}}, "sk")
    _handle_payment_succeeded(w.db, intent)
    w.db.refresh(payment)
    assert payment.tip_amount == Decimal("2.50")
    assert payment.amount == order.total  # the bill is unchanged
    assert w.db.get(Order, order.id).status == OrderStatus.CONFIRMED


# ---------------------------------------------------------------- cash tips and cash-up

def test_cash_tips_declared_at_shift_close_are_not_a_surplus(world):
    w = world
    headers, _ = pos_headers(w)
    shift = w.client.post(f"{API}/pos/shifts/open", headers=headers, json={"starting_float": "50.00"}).json()["shift_id"]
    order = counter_order(w, headers)
    w.client.post(f"{API}/pos/orders/{order['order_id']}/pay-cash", headers=headers)
    closed = w.client.post(f"{API}/pos/shifts/{shift}/close", headers=headers, json={"counted_cash": "68.20", "cash_tips": "5.00"})
    assert closed.status_code == 200, closed.text
    z = closed.json()
    assert Decimal(z["expected_cash"]) == Decimal("63.20") and Decimal(z["variance"]) == Decimal("0.00")
    assert Decimal(z["cash_tips"]) == Decimal("5.00")


def test_a_handheld_server_cashes_up_at_clock_out(world):
    w = world
    token = w.client.post(f"{API}/admin/devices", params={"restaurant_id": w.a.rid}, headers=header(w.a.admin), json={"label": "Server 1", "kind": "HANDHELD"}).json()["device_token"]
    headers, _ = pos_headers(w, device_token=token)
    w.client.post(f"{API}/pos/time-entries/clock-in", headers=headers)
    order = counter_order(w, headers)
    w.client.post(f"{API}/pos/orders/{order['order_id']}/pay-cash", headers=headers)
    r = w.client.post(f"{API}/pos/time-entries/clock-out", headers=headers, json={"counted_cash": "16.20", "cash_tips": "3.00"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert Decimal(out["expected_cash"]) == Decimal("13.20")
    assert Decimal(out["variance"]) == Decimal("0.00")  # 16.20 counted − 3.00 tips − 13.20 taken


def test_clocking_out_without_a_cash_up_still_works(world):
    headers, _ = pos_headers(world)
    world.client.post(f"{API}/pos/time-entries/clock-in", headers=headers)
    r = world.client.post(f"{API}/pos/time-entries/clock-out", headers=headers)
    assert r.status_code == 200 and r.json()["counted_cash"] is None


# ---------------------------------------------------------------- pooling + ledger

def _seed_tips(w):
    """Staff: card tips 30 + cash 0, 4h. Admin: card 0, cash tips 10, 1h — within the last day."""
    now = datetime.now(UTC)
    for user, card, cash, hours in ((w.a.staff, "30.00", "0.00", 4), (w.a.admin, "0.00", "10.00", 1)):
        if Decimal(card) > 0:
            w.db.add(Payment(
                order_id=None, restaurant_id=w.a.rid, amount=Decimal("20"), currency="usd", payment_method=PaymentMethod.CARD, provider="STRIPE",
                status=PaymentStatus.COMPLETED, staff_user_id=user.id, tip_amount=Decimal(card),
            ))
        w.db.add(TimeEntry(restaurant_id=w.a.rid, user_id=user.id, clock_in_at=now - timedelta(hours=hours + 1), clock_out_at=now - timedelta(hours=1), cash_tips=Decimal(cash)))
    w.db.commit()


def report(w, **extra):
    now = datetime.now(UTC)
    params = {"restaurant_id": w.a.rid, "start": (now - timedelta(days=1)).isoformat(), "end": (now + timedelta(hours=1)).isoformat(), **extra}
    return w.client.get(f"{API}/admin/tips/report", params=params, headers=header(w.a.admin))


@pytest.mark.parametrize(("mode", "staff_pays", "admin_pays"), [("KEEP", "30.00", "10.00"), ("POOL_EQUAL", "20.00", "20.00"), ("POOL_HOURS", "32.00", "8.00")])
def test_pooling_policies(world, mode, staff_pays, admin_pays):
    w = world
    settings_patch(w, tip_pool_mode=mode)
    _seed_tips(w)
    r = report(w)
    assert r.status_code == 200, r.text
    rows = {row["user_id"]: row for row in r.json()["rows"]}
    assert Decimal(r.json()["total"]) == Decimal("40.00")
    assert Decimal(rows[w.a.staff.id]["payout"]) == Decimal(staff_pays)
    assert Decimal(rows[w.a.admin.id]["payout"]) == Decimal(admin_pays)
    assert sum(Decimal(x["payout"]) for x in rows.values()) == Decimal("40.00")  # nothing lost to rounding


def test_finalizing_writes_the_ledger_once(world):
    w = world
    settings_patch(w, tip_pool_mode="POOL_EQUAL")
    _seed_tips(w)
    now = datetime.now(UTC)
    body = {"start": (now - timedelta(days=1)).isoformat(), "end": (now + timedelta(hours=1)).isoformat()}
    first = w.client.post(f"{API}/admin/tips/finalize", params={"restaurant_id": w.a.rid}, headers=header(w.a.admin), json=body)
    assert first.status_code == 200, first.text
    assert w.client.post(f"{API}/admin/tips/finalize", params={"restaurant_id": w.a.rid}, headers=header(w.a.admin), json=body).status_code == 409
    history = w.client.get(f"{API}/admin/tips/history", params={"restaurant_id": w.a.rid}, headers=header(w.a.admin)).json()
    assert sorted(Decimal(h["amount"]) for h in history) == [Decimal("20.00"), Decimal("20.00")]
    assert report(w).json()["already_finalized"] is True


def test_tip_routes_need_the_flag(world):
    FeatureService(world.db).set(world.a.rid, "tips", False, None, actor_label="test")
    world.db.commit()
    assert report(world).status_code == 403


def test_the_employee_report_carries_tips(world):
    w = world
    _seed_tips(w)
    w.db.add(Payment(  # a cash sale so the staff member appears in the takings report at all
        order_id=None, restaurant_id=w.a.rid, amount=Decimal("5"), currency="usd", payment_method=PaymentMethod.CASH, provider="MANUAL",
        status=PaymentStatus.COMPLETED, staff_user_id=w.a.staff.id,
    ))
    w.db.commit()
    rows = w.client.get(f"{API}/admin/analytics/employees", params={"restaurant_id": w.a.rid, "preset": "last_7_days"}, headers=header(w.a.admin))
    assert rows.status_code == 200, rows.text
    staff_row = next(r for r in rows.json() if r["user_id"] == w.a.staff.id)
    assert Decimal(staff_row["card_tips"]) == Decimal("30.00")


# ---------------------------------------------------------------- terminal tipping setup

class _Terminal:
    calls: list = []

    def __init__(self, api_key):
        outer = _Terminal
        def make(kind):
            def create(params, options=None):
                outer.calls.append((kind, "create", params))
                return SimpleNamespace(id=f"{kind}_1")
            def update(rid, params, options=None):
                outer.calls.append((kind, "update", rid, params))
                return SimpleNamespace(id=rid)
            return SimpleNamespace(create=create, update=update)
        self.v1 = SimpleNamespace(terminal=SimpleNamespace(locations=make("tml"), configurations=make("tmc")))


def test_terminal_sync_creates_a_location_and_tipping_configuration(world, monkeypatch):
    w = world
    monkeypatch.setattr(stripe, "StripeClient", _Terminal)
    monkeypatch.setattr(settings, "PAYMENT_PROVIDER", "stripe")
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_fake")
    _Terminal.calls = []
    w.db.get(Restaurant, w.a.rid).stripe_account_id = "acct_x"
    w.db.commit()
    settings_patch(w, tips_enabled=True, tip_presets=[10, 15, 20])
    r = w.client.post(f"{API}/admin/settings/terminal/sync", params={"restaurant_id": w.a.rid}, headers=header(w.a.admin))
    assert r.status_code == 200, r.text
    config = next(c for c in _Terminal.calls if c[0] == "tmc" and c[1] == "create")[2]
    assert config["tipping"] == {"usd": {"percentages": [10, 15, 20]}, "cad": {"percentages": [10, 15, 20]}}
    assert ("tml", "update", "tml_1", {"configuration_overrides": "tmc_1"}) in _Terminal.calls
    # Turning tips off removes the tipping config from the reader.
    settings_patch(w, tips_enabled=False)
    w.client.post(f"{API}/admin/settings/terminal/sync", params={"restaurant_id": w.a.rid}, headers=header(w.a.admin))
    assert ("tmc", "update", "tmc_1", {"tipping": ""}) in _Terminal.calls
