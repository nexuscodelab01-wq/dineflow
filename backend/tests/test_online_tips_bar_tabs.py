"""Tips added at online checkout (delivery / pickup) and table-less bar tabs."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
import stripe

from app.core.config import settings
from app.db.session import get_db
from app.main import app
from app.models.enums import PaymentStatus
from app.models.payment import Payment
from app.models.restaurant import Restaurant
from app.models.restaurant_table import RestaurantTable
from app.models.restaurant_user import RestaurantUser
from app.models.table_session import TableSession
from app.services.feature_service import FeatureService
from tests.conftest import override_get_db
from tests.tenants import header, make_tenant

API = "/api/v1"


@pytest.fixture
def world(client, db):
    app.dependency_overrides[get_db] = override_get_db(db)
    a = make_tenant(db, "Alpha")
    for flag in ("pos", "qr_table_ordering", "tips"):
        FeatureService(db).set(a.rid, flag, True, None, actor_label="test")
    db.get(Restaurant, a.rid).tips_enabled = True
    db.commit()
    mid = db.query(RestaurantUser).filter_by(restaurant_id=a.rid, user_id=a.staff.id).one().id
    client.post(f"{API}/admin/devices/staff/{mid}/pin", params={"restaurant_id": a.rid}, headers=header(a.admin), json={"pin": "1111"})
    token = client.post(f"{API}/admin/devices", params={"restaurant_id": a.rid}, headers=header(a.admin), json={"label": "Till"}).json()["device_token"]
    login = client.post(f"{API}/pos/auth/pin-login", headers={"Authorization": f"Bearer {token}"}, json={"pin": "1111"}).json()
    yield type("W", (), {"client": client, "db": db, "a": a, "h": {"Authorization": f"Bearer {login['pos_session_token']}"}, "device": {"Authorization": f"Bearer {token}"}})
    app.dependency_overrides.clear()


def order(w, order_type="PICKUP", tip=None, **extra):
    body = {
        "restaurant_id": w.a.rid, "order_type": order_type, "customer_name": "Pat", "customer_email": w.a.customer.email, "customer_phone": "555",
        "items": [{"menu_item_id": w.a.item.id, "quantity": 1, "modifier_option_ids": []}], **extra,
    }
    if tip is not None:
        body["tip"] = tip
    if order_type == "DELIVERY":
        body["delivery_address"] = {"street": "1 Main", "city": "Town", "postal_code": "12345"}
    return w.client.post(f"{API}/orders", headers=header(w.a.customer), json=body)


# ---------------------------------------------------------------- online tips

def test_a_delivery_tip_rides_on_the_payment_but_not_the_bill(world):
    w = world
    r = order(w, "DELIVERY", tip="3.00")
    assert r.status_code == 201, r.text
    assert r.json()["total"] == "15.20"  # 12.00 + 10% tax + 2.00 delivery — no tip in the bill
    payment = w.db.query(Payment).filter_by(order_id=r.json()["id"]).one()
    assert payment.amount == Decimal("15.20") and payment.tip_amount == Decimal("3.00")
    assert r.json()["payments"][0]["tip_amount"] == "3.00"


def test_the_card_is_charged_bill_plus_tip(world, monkeypatch):
    w = world
    seen = []

    class Fake:
        def __init__(self, key):
            self.v1 = SimpleNamespace(payment_intents=SimpleNamespace(create=lambda p, options=None: (seen.append(p), SimpleNamespace(id="pi_t", client_secret="s"))[1]))

    monkeypatch.setattr(stripe, "StripeClient", Fake)
    monkeypatch.setattr(settings, "PAYMENT_PROVIDER", "stripe")
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_x")
    w.db.get(Restaurant, w.a.rid).stripe_account_id = "acct_x"
    w.db.commit()
    assert order(w, tip="2.50").status_code == 201
    assert seen[0]["amount"] == 1570  # 13.20 + 2.50


def test_online_tip_rules(world):
    w = world
    assert order(w, "PICKUP", tip="-1").status_code == 422
    assert order(w, "PICKUP", tip="50").status_code == 400  # bigger than the order itself
    assert order(w, "PICKUP", tip="2", pay_later=True).status_code == 400
    w.db.get(Restaurant, w.a.rid).tips_enabled = False
    w.db.commit()
    assert order(w, "PICKUP", tip="2").status_code == 400
    assert order(w, "PICKUP").status_code == 201  # no tip is always fine


def test_online_tips_are_reported_unassigned_and_pooled_only_when_tips_are_pooled(world):
    w = world
    order(w, "DELIVERY", tip="4.00")
    now = datetime.now(UTC)
    params = {"restaurant_id": w.a.rid, "start": (now - timedelta(days=1)).isoformat(), "end": (now + timedelta(hours=1)).isoformat()}
    keep = w.client.get(f"{API}/admin/tips/report", params=params, headers=header(w.a.admin)).json()
    assert keep["unassigned"] == "4.00" and keep["total"] == "0.00"  # nobody's to keep
    w.db.get(Restaurant, w.a.rid).tip_pool_mode = "POOL_EQUAL"
    w.db.add(Payment(order_id=None, restaurant_id=w.a.rid, amount=Decimal("10"), currency="usd", payment_method="CARD", provider="STRIPE", status=PaymentStatus.COMPLETED, staff_user_id=w.a.staff.id, tip_amount=Decimal("2.00")))
    w.db.commit()
    pooled = w.client.get(f"{API}/admin/tips/report", params=params, headers=header(w.a.admin)).json()
    assert pooled["total"] == "6.00" and pooled["rows"][0]["payout"] == "6.00"  # the server's 2.00 plus the 4.00 delivery tip


# ---------------------------------------------------------------- bar tabs

def test_a_bar_tab_works_like_a_table_without_one(world):
    w = world
    made = w.client.post(f"{API}/pos/tabs", headers=w.h, json={"name": "Mike at the bar"})
    assert made.status_code == 201, made.text
    tab = made.json()
    assert tab["is_bar_tab"] is True and tab["table_number"] == "Tab 1"
    sid = tab["session_id"]
    r = w.client.post(f"{API}/pos/table-sessions/{sid}/orders", headers=w.h, json={"items": [{"menu_item_id": w.a.item.id, "quantity": 2, "modifier_option_ids": []}]})
    assert r.status_code == 200, r.text
    detail = w.client.get(f"{API}/pos/table-sessions/{sid}", headers=w.h).json()
    assert detail["tab_name"] == "Mike at the bar" and detail["total"] == "26.40"
    check = w.client.get(f"{API}/pos/table-sessions/{sid}/receipt", headers=w.h).json()
    assert check["reference"] == "Tab · Mike at the bar" and check["title"] == "Check"
    assert w.client.post(f"{API}/pos/table-sessions/{sid}/pay-cash", headers=w.h, json={"mode": "EVEN", "parts_remaining": 2}).status_code == 204
    assert w.client.post(f"{API}/pos/table-sessions/{sid}/pay-cash", headers=w.h).status_code == 204
    assert w.db.get(TableSession, sid).state == "CLOSED"


def test_the_stand_in_table_never_shows_up_anywhere_else(world):
    w = world
    w.client.post(f"{API}/pos/tabs", headers=w.h, json={"name": "Mike"})
    w.client.post(f"{API}/pos/tabs", headers=w.h, json={"name": "Sara"})
    assert [t["table_number"] for t in w.client.get(f"{API}/pos/tables", headers=w.device).json()] == ["A1"]
    stand_ins = w.db.query(RestaurantTable).filter_by(restaurant_id=w.a.rid, ephemeral=True).all()
    assert [t.table_number for t in stand_ins] == ["Tab 1", "Tab 2"] and not any(t.is_active for t in stand_ins)
    admin_tables = w.client.get(f"{API}/admin/tables", params={"restaurant_id": w.a.rid, "include_inactive": True}, headers=header(w.a.admin)).json()
    assert {t["table_number"] for t in admin_tables} == {"A1"}
    open_tabs = w.client.get(f"{API}/pos/table-sessions/open", headers=w.device).json()["sessions"]
    assert {s["tab_name"] for s in open_tabs} == {"Mike", "Sara"} and all(s["is_bar_tab"] for s in open_tabs)


def test_a_bar_tab_needs_a_name_and_a_flag(world):
    w = world
    assert w.client.post(f"{API}/pos/tabs", headers=w.h, json={"name": "  "}).status_code in (400, 422)
    FeatureService(w.db).set(w.a.rid, "pos", False, None, actor_label="test")
    w.db.commit()
    assert w.client.post(f"{API}/pos/tabs", headers=w.h, json={"name": "Mike"}).status_code in (401, 403)


def test_another_restaurants_tab_cant_be_reached_through_a_bar_tab_id(world):
    w = world
    b = make_tenant(w.db, "Bravo")
    FeatureService(w.db).set(b.rid, "pos", True, None, actor_label="test")
    mid = w.db.query(RestaurantUser).filter_by(restaurant_id=b.rid, user_id=b.staff.id).one().id
    w.client.post(f"{API}/admin/devices/staff/{mid}/pin", params={"restaurant_id": b.rid}, headers=header(b.admin), json={"pin": "3333"})
    token = w.client.post(f"{API}/admin/devices", params={"restaurant_id": b.rid}, headers=header(b.admin), json={"label": "T"}).json()["device_token"]
    login = w.client.post(f"{API}/pos/auth/pin-login", headers={"Authorization": f"Bearer {token}"}, json={"pin": "3333"}).json()
    theirs = {"Authorization": f"Bearer {login['pos_session_token']}"}
    sid = w.client.post(f"{API}/pos/tabs", headers=w.h, json={"name": "Mike"}).json()["session_id"]
    assert w.client.get(f"{API}/pos/table-sessions/{sid}", headers=theirs).status_code == 404
    assert w.client.get(f"{API}/pos/table-sessions/{sid}/receipt", headers=theirs).status_code == 404
