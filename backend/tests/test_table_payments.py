"""Paying a table's tab: online (mock/Stripe) and staff-marked cash, and that it's what finally makes
dine-in revenue show up in analytics (see AnalyticsRepository._revenue's docstring)."""

from decimal import Decimal

import pytest

from app.core.config import settings
from app.db.session import get_db
from app.main import app
from app.models.enums import PaymentMethod, PaymentStatus, RoleName, TableStatus
from app.models.payment import Payment
from app.models.table_session import CLOSED, OPEN, TableSession
from app.services.feature_service import FeatureService
from tests.conftest import override_get_db
from tests.tenants import header, make_tenant, make_user

API = "/api/v1"


@pytest.fixture
def world(client, db):
    app.dependency_overrides[get_db] = override_get_db(db)
    a, b = make_tenant(db, "Alpha"), make_tenant(db, "Bravo")
    boss = make_user(db, "boss-pay@iso-demo.com", RoleName.SUPER_ADMIN)
    for t in (a, b):
        FeatureService(db).set(t.rid, "qr_table_ordering", True, boss)
        t.table.status = TableStatus.OCCUPIED
    db.flush()
    yield type("W", (), {"client": client, "db": db, "a": a, "b": b, "boss": boss})
    app.dependency_overrides.clear()


def join(w, t, name=None):
    r = w.client.post(f"{API}/t/{t.table.qr_token}/join", params={"restaurant_id": t.rid}, json={"name": name})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def send(w, t, h, qty=1):
    r = w.client.post(f"{API}/table-session/orders", headers=h, json={
        "items": [{"menu_item_id": t.item.id, "quantity": qty, "modifier_option_ids": []}]})
    assert r.status_code == 201, r.text
    return r


def pay(w, h):
    return w.client.post(f"{API}/table-session/pay", headers=h)


def session_id_for(w, t):
    return w.db.query(TableSession).filter_by(table_id=t.table.id, state=OPEN).one().id


# ------------------------------------------------------------------ online (mock) payment

def test_paying_settles_instantly_under_mock_and_closes_the_tab(world):
    w = world
    sam = join(w, w.a, "Sam")
    send(w, w.a, sam, qty=2)
    sid = session_id_for(w, w.a)

    r = pay(w, sam)
    assert r.status_code == 200 and r.json() == {"client_secret": None, "closed": True}

    session = w.db.get(TableSession, sid)
    assert session.state == CLOSED
    w.db.refresh(w.a.table)
    assert w.a.table.status == TableStatus.CLEANING

    payment = w.db.query(Payment).filter_by(table_session_id=sid).one()
    assert payment.status == PaymentStatus.COMPLETED
    assert payment.payment_method == PaymentMethod.MOCK
    assert payment.order_id is None
    assert payment.restaurant_id == w.a.rid
    assert payment.amount == session_total_before_close(w, w.a)


def session_total_before_close(w, t):
    # 2x the seeded item's price with tax, matching tenants.make_tenant's $12.00 item and 10% tax.
    return (Decimal("12.00") * 2 * Decimal("1.10")).quantize(Decimal("0.01"))


def test_refuses_to_pay_a_zero_total_tab(world):
    w = world
    sam = join(w, w.a, "Sam")
    r = pay(w, sam)
    assert r.status_code == 400 and "nothing" in r.json()["detail"].lower()


def test_the_guest_pass_stops_working_the_moment_the_tab_is_paid(world):
    """Paying closes the session — same as staff closing it (test_table_ordering.py) — so the guest's
    own pass is rejected on any further call, this one included."""
    w = world
    sam = join(w, w.a, "Sam")
    send(w, w.a, sam)
    assert pay(w, sam).status_code == 200
    assert pay(w, sam).status_code == 401


def test_refuses_a_second_payment_while_one_is_already_in_flight(world):
    w = world
    sam = join(w, w.a, "Sam")
    send(w, w.a, sam)
    sid = session_id_for(w, w.a)
    # Simulate a real (Stripe) payment mid-flight — the mock provider never leaves this state itself.
    w.db.add(Payment(
        table_session_id=sid, order_id=None, restaurant_id=w.a.rid, amount=Decimal("13.20"),
        status=PaymentStatus.REQUIRES_ACTION, payment_method=PaymentMethod.CARD, provider="STRIPE",
        provider_intent_id="pi_in_flight",
    ))
    w.db.commit()

    r = pay(w, sam)
    assert r.status_code == 400 and "already in progress" in r.json()["detail"].lower()


def test_a_restaurant_not_connected_to_stripe_cannot_take_a_real_table_payment(world, monkeypatch):
    w = world
    sam = join(w, w.a, "Sam")
    send(w, w.a, sam)
    monkeypatch.setattr(settings, "PAYMENT_PROVIDER", "stripe")

    r = pay(w, sam)
    assert r.status_code == 400
    assert "connected a stripe account" in r.json()["detail"].lower()


# ------------------------------------------------------------------ staff-marked cash

def test_staff_can_mark_a_tab_paid_in_cash_and_it_closes(world):
    w = world
    sam = join(w, w.a, "Sam")
    send(w, w.a, sam, qty=1)
    sid = session_id_for(w, w.a)
    staff = header(w.a.staff)

    r = w.client.post(f"{API}/admin/table-sessions/{sid}/mark-paid", params={"restaurant_id": w.a.rid}, headers=staff, json={"method": "CASH"})
    assert r.status_code == 204, r.text

    assert w.db.get(TableSession, sid).state == CLOSED
    payment = w.db.query(Payment).filter_by(table_session_id=sid).one()
    assert payment.status == PaymentStatus.COMPLETED and payment.payment_method == PaymentMethod.CASH
    assert payment.provider == "MANUAL"


def test_cannot_mark_another_restaurants_tab_paid(world):
    w = world
    join(w, w.a, "Sam")
    sid = session_id_for(w, w.a)
    r = w.client.post(
        f"{API}/admin/table-sessions/{sid}/mark-paid", params={"restaurant_id": w.b.rid}, headers=header(w.b.staff), json={"method": "CASH"}
    )
    assert r.status_code == 404


def test_marking_an_empty_tab_paid_is_refused(world):
    w = world
    join(w, w.a, "Sam")
    sid = session_id_for(w, w.a)
    r = w.client.post(f"{API}/admin/table-sessions/{sid}/mark-paid", params={"restaurant_id": w.a.rid}, headers=header(w.a.staff), json={"method": "CASH"})
    assert r.status_code == 400


# ------------------------------------------------------------------ refunding a tab (API-level only — no UI yet)

def refund(w, t, sid):
    return w.client.post(f"{API}/admin/table-sessions/{sid}/refund", params={"restaurant_id": t.rid}, headers=header(t.staff))


def test_refunding_a_closed_paid_tab_marks_its_payment_refunded(world):
    w = world
    sam = join(w, w.a, "Sam")
    send(w, w.a, sam, qty=1)
    sid = session_id_for(w, w.a)
    assert pay(w, sam).status_code == 200

    r = refund(w, w.a, sid)
    assert r.status_code == 204, r.text
    payment = w.db.query(Payment).filter_by(table_session_id=sid).one()
    assert payment.status == PaymentStatus.REFUNDED


def test_refusing_to_refund_a_tab_thats_still_open(world):
    w = world
    join(w, w.a, "Sam")
    sid = session_id_for(w, w.a)
    r = refund(w, w.a, sid)
    assert r.status_code == 400


def test_refusing_to_refund_a_tab_with_no_completed_payment(world):
    w = world
    sam = join(w, w.a, "Sam")
    send(w, w.a, sam, qty=1)
    sid = session_id_for(w, w.a)
    staff = header(w.a.staff)
    # Closed without ever being paid (e.g. a comped table).
    assert w.client.post(f"{API}/admin/table-sessions/{sid}/close", params={"restaurant_id": w.a.rid}, headers=staff).status_code == 204

    r = refund(w, w.a, sid)
    assert r.status_code == 400


def test_only_the_restaurants_own_staff_can_refund_its_tabs(world):
    w = world
    sam = join(w, w.a, "Sam")
    send(w, w.a, sam, qty=1)
    sid = session_id_for(w, w.a)
    assert pay(w, sam).status_code == 200

    r = w.client.post(f"{API}/admin/table-sessions/{sid}/refund", params={"restaurant_id": w.b.rid}, headers=header(w.b.staff))
    assert r.status_code == 404


# ------------------------------------------------------------------ the actual dine-in-revenue fix

def test_a_paid_table_session_counts_toward_todays_revenue(world):
    """The actual regression test for "dine-in revenue is invisible" (ROADMAP §4.1): a table-session
    Payment has no order_id, so the old Order-joined revenue query would have missed it entirely."""
    w = world
    sam = join(w, w.a, "Sam")
    send(w, w.a, sam, qty=1)
    expected = (Decimal("12.00") * Decimal("1.10")).quantize(Decimal("0.01"))
    assert pay(w, sam).status_code == 200

    r = w.client.get(f"{API}/admin/dashboard", params={"restaurant_id": w.a.rid}, headers=header(w.a.admin))
    assert r.status_code == 200
    assert Decimal(r.json()["today_revenue"]) == expected
