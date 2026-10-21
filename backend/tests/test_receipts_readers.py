"""Receipts (data, printer bytes, email), device printer settings, and server-driven card readers."""

import base64
from decimal import Decimal
from types import SimpleNamespace

import pytest
import stripe
from sqlalchemy import text

from app.api.routes.webhooks import _handle_payment_succeeded, _handle_reader_action_failed
from app.core.config import settings
from app.core.escpos import DRAWER_KICK
from app.db.session import get_db
from app.main import app
from app.models.enums import OrderStatus, PaymentStatus
from app.models.order import Order
from app.models.payment import Payment
from app.models.restaurant import Restaurant
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
    for flag in ("pos", "qr_table_ordering"):
        FeatureService(db).set(a.rid, flag, True, None, actor_label="test")
    r = db.get(Restaurant, a.rid)
    r.address, r.city, r.state, r.postal_code, r.phone = "1 Pike St", "Seattle", "WA", "98101", "555-0100"
    db.commit()
    mid = db.query(RestaurantUser).filter_by(restaurant_id=a.rid, user_id=a.staff.id).one().id
    client.post(f"{API}/admin/devices/staff/{mid}/pin", params={"restaurant_id": a.rid}, headers=header(a.admin), json={"pin": "1111"})
    paired = client.post(f"{API}/admin/devices", params={"restaurant_id": a.rid}, headers=header(a.admin), json={"label": "Till"}).json()
    login = client.post(f"{API}/pos/auth/pin-login", headers={"Authorization": f"Bearer {paired['device_token']}"}, json={"pin": "1111"}).json()
    yield type("W", (), {
        "client": client, "db": db, "a": a, "device_id": paired["device_id"], "login": login,
        "h": {"Authorization": f"Bearer {login['pos_session_token']}"},
    })
    app.dependency_overrides.clear()


def counter(w, qty=1):
    r = w.client.post(f"{API}/pos/orders", headers=w.h, json={"items": [{"menu_item_id": w.a.item.id, "quantity": qty, "modifier_option_ids": []}]})
    assert r.status_code == 201, r.text
    return r.json()["order_id"]


def seat_with_round(w, qty=1):
    sid = w.client.post(f"{API}/pos/tables/{w.a.table.id}/seat", headers=w.h, json={"party_size": 2, "tab_name": "Mike"}).json()["session_id"]
    w.client.post(f"{API}/pos/table-sessions/{sid}/orders", headers=w.h, json={"items": [{"menu_item_id": w.a.item.id, "quantity": qty, "modifier_option_ids": []}]})
    return sid


# ---------------------------------------------------------------- receipts

def test_an_order_receipt_has_everything_on_it(world):
    w = world
    oid = counter(w, qty=2)
    w.client.post(f"{API}/pos/orders/{oid}/pay-cash", headers=w.h)
    r = w.client.get(f"{API}/pos/orders/{oid}/receipt", headers=w.h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["restaurant_name"] == "Alpha Kitchen" and body["address_lines"] == ["1 Pike St", "Seattle WA 98101"] and body["phone"] == "555-0100"
    assert body["title"] == "Receipt" and body["lines"][0]["quantity"] == 2
    assert (body["subtotal"], body["tax"], body["total"], body["paid"], body["balance"]) == ("24.00", "2.40", "26.40", "26.40", "0.00")
    assert body["served_by"] == "Alpha" and body["payments"][0]["method"] == "CASH"


def test_an_open_tab_prints_as_a_check_and_a_paid_one_as_a_receipt(world):
    w = world
    sid = seat_with_round(w)
    check = w.client.get(f"{API}/pos/table-sessions/{sid}/receipt", headers=w.h).json()
    assert check["title"] == "Check" and check["reference"] == "Table A1 · Mike" and check["balance"] == "13.20"
    w.client.post(f"{API}/pos/table-sessions/{sid}/pay-cash", headers=w.h, json={"mode": "AMOUNT", "amount": "5"})
    assert w.client.get(f"{API}/pos/table-sessions/{sid}/receipt", headers=w.h).json()["balance"] == "8.20"
    w.client.post(f"{API}/pos/table-sessions/{sid}/pay-cash", headers=w.h)
    done = w.client.get(f"{API}/pos/table-sessions/{sid}/receipt", headers=w.h).json()
    assert done["title"] == "Receipt" and done["paid"] == "13.20" and len(done["payments"]) == 2


def test_the_printer_bytes_are_a_real_escpos_receipt(world):
    w = world
    oid = counter(w)
    data = base64.b64decode(w.client.get(f"{API}/pos/orders/{oid}/receipt/escpos", headers=w.h).json()["data"])
    assert data.startswith(b"\x1b@") and b"ALPHA KITCHEN"[:5].lower() in data.lower() and b"TOTAL" in data and data.endswith(b"\x1dVB\x00")
    assert DRAWER_KICK not in data  # nothing wired up


def test_the_drawer_only_kicks_when_the_till_has_one_and_it_is_asked_for(world):
    w = world
    oid = counter(w)
    url = f"{API}/pos/orders/{oid}/receipt/escpos"
    assert DRAWER_KICK not in base64.b64decode(w.client.get(url, params={"kick": True}, headers=w.h).json()["data"])
    set_ = w.client.patch(f"{API}/admin/devices/{w.device_id}", params={"restaurant_id": w.a.rid}, headers=header(w.a.admin), json={"cash_drawer": True, "printer_host": " 192.168.0.50 ", "auto_print": True})
    assert set_.status_code == 200 and set_.json()["printer"] == {"host": "192.168.0.50", "port": 9100, "cash_drawer": True, "auto_print": True}
    assert DRAWER_KICK in base64.b64decode(w.client.get(url, params={"kick": True}, headers=w.h).json()["data"])
    assert DRAWER_KICK not in base64.b64decode(w.client.get(url, headers=w.h).json()["data"])


def test_the_till_learns_its_printer_at_pin_login(world):
    w = world
    w.client.patch(f"{API}/admin/devices/{w.device_id}", params={"restaurant_id": w.a.rid}, headers=header(w.a.admin), json={"printer_host": "10.0.0.9", "printer_port": 9101})
    token = w.client.post(f"{API}/admin/devices", params={"restaurant_id": w.a.rid}, headers=header(w.a.admin), json={"label": "Other"}).json()["device_token"]
    assert w.client.post(f"{API}/pos/auth/pin-login", headers={"Authorization": f"Bearer {token}"}, json={"pin": "1111"}).json()["printer"]["host"] is None
    listed = w.client.get(f"{API}/admin/devices", params={"restaurant_id": w.a.rid}, headers=header(w.a.admin)).json()
    assert {d["printer"]["host"] for d in listed} == {"10.0.0.9", None}


def test_a_receipt_can_be_emailed(world):
    w = world
    oid = counter(w)
    w.client.post(f"{API}/pos/orders/{oid}/pay-cash", headers=w.h)
    assert w.client.post(f"{API}/pos/orders/{oid}/receipt/email", headers=w.h, json={"email": "pat@example.com"}).status_code == 204
    rows = w.db.execute(text("SELECT payload FROM jobs WHERE type = 'send_email' ORDER BY id")).all()
    mails = [r.payload for r in rows if r.payload["to"] == "pat@example.com"]
    assert mails and "receipt" in mails[0]["subject"].lower() and "13.20" in mails[0]["text"]
    assert w.client.post(f"{API}/pos/orders/{oid}/receipt/email", headers=w.h, json={"email": "not-an-email"}).status_code == 422


def test_an_unpaid_tab_has_no_receipt_to_email(world):
    w = world
    sid = seat_with_round(w)
    assert w.client.post(f"{API}/pos/table-sessions/{sid}/receipt/email", headers=w.h, json={"email": "pat@example.com"}).status_code == 400


def test_another_restaurants_till_cannot_read_a_receipt(world):
    w = world
    oid = counter(w)
    b = make_tenant(w.db, "Bravo")
    FeatureService(w.db).set(b.rid, "pos", True, None, actor_label="test")
    mid = w.db.query(RestaurantUser).filter_by(restaurant_id=b.rid, user_id=b.staff.id).one().id
    w.client.post(f"{API}/admin/devices/staff/{mid}/pin", params={"restaurant_id": b.rid}, headers=header(b.admin), json={"pin": "2222"})
    token = w.client.post(f"{API}/admin/devices", params={"restaurant_id": b.rid}, headers=header(b.admin), json={"label": "T"}).json()["device_token"]
    login = w.client.post(f"{API}/pos/auth/pin-login", headers={"Authorization": f"Bearer {token}"}, json={"pin": "2222"}).json()
    theirs = {"Authorization": f"Bearer {login['pos_session_token']}"}
    assert w.client.get(f"{API}/pos/orders/{oid}/receipt", headers=theirs).status_code == 404
    assert w.client.get(f"{API}/pos/orders/{oid}/receipt/escpos", headers=theirs).status_code == 404
    assert w.client.post(f"{API}/pos/orders/{oid}/receipt/email", headers=theirs, json={"email": "x@example.com"}).status_code == 404


# ---------------------------------------------------------------- server-driven readers

class FakeStripe:
    reader_error = False
    calls: list = []
    readers = [SimpleNamespace(id="tmr_1", label="Counter reader", status="online", device_type="bbpos_wisepos_e")]

    def __init__(self, api_key):
        outer = FakeStripe

        def rec(name, ret=None):
            def f(*args, **kw):
                outer.calls.append((name, args, kw))
                return ret(*args, **kw) if callable(ret) else ret
            return f

        def process(reader_id, params, options=None):
            outer.calls.append(("process", reader_id, params))
            if outer.reader_error:
                raise stripe.StripeError("The reader is busy")
            return SimpleNamespace(id=reader_id)

        readers = SimpleNamespace(
            list=lambda params, options=None: SimpleNamespace(data=outer.readers),
            create=lambda params, options=None: SimpleNamespace(id="tmr_new", label=params["label"], status="offline", device_type="bbpos_wisepos_e"),
            delete=rec("delete"), process_payment_intent=process, cancel_action=rec("cancel_action"),
        )
        locs = SimpleNamespace(create=lambda p, options=None: SimpleNamespace(id="tml_1"), update=lambda i, p, options=None: SimpleNamespace(id=i))
        cfgs = SimpleNamespace(create=lambda p, options=None: SimpleNamespace(id="tmc_1"), update=lambda i, p, options=None: SimpleNamespace(id=i))
        pis = SimpleNamespace(
            create=lambda params, options=None: SimpleNamespace(id=f"pi_{len(outer.calls)}", client_secret="sec"),
            cancel=rec("pi_cancel"),
        )
        self.v1 = SimpleNamespace(terminal=SimpleNamespace(readers=readers, locations=locs, configurations=cfgs), payment_intents=pis)


@pytest.fixture
def live(world, monkeypatch):
    monkeypatch.setattr(stripe, "StripeClient", FakeStripe)
    monkeypatch.setattr(settings, "PAYMENT_PROVIDER", "stripe")
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_fake")
    FakeStripe.reader_error, FakeStripe.calls = False, []
    r = world.db.get(Restaurant, world.a.rid)
    r.stripe_account_id, r.stripe_terminal_location_id = "acct_x", "tml_1"
    world.db.commit()
    return world


def test_no_readers_are_listed_without_stripe(world):
    assert world.client.get(f"{API}/pos/readers", headers=world.h).json() == []


def test_the_till_lists_the_restaurants_readers(live):
    r = live.client.get(f"{API}/pos/readers", headers=live.h).json()
    assert r == [{"id": "tmr_1", "label": "Counter reader", "status": "online", "device_type": "bbpos_wisepos_e"}]


def test_an_admin_registers_and_removes_a_reader(live):
    w = live
    made = w.client.post(f"{API}/admin/terminal/readers", params={"restaurant_id": w.a.rid}, headers=header(w.a.admin), json={"registration_code": "apple-grape-pear", "label": "Bar"})
    assert made.status_code == 201 and made.json()["id"] == "tmr_new"
    assert w.client.delete(f"{API}/admin/terminal/readers/tmr_1", params={"restaurant_id": w.a.rid}, headers=header(w.a.admin)).status_code == 204
    assert w.client.delete(f"{API}/admin/terminal/readers/tmr_zzz", params={"restaurant_id": w.a.rid}, headers=header(w.a.admin)).status_code == 404


def test_a_sale_is_sent_to_the_reader_and_finished_by_the_webhook(live):
    w = live
    oid = counter(w)
    r = w.client.post(f"{API}/pos/orders/{oid}/pay-reader", headers=w.h, json={"reader_id": "tmr_1"})
    assert r.status_code == 200, r.text
    assert r.json()["client_secret"] is None and r.json()["payment_id"]
    assert any(c[0] == "process" and c[1] == "tmr_1" for c in FakeStripe.calls)
    payment = w.db.get(Payment, r.json()["payment_id"])
    assert payment.status == PaymentStatus.REQUIRES_ACTION and payment.staff_user_id == w.a.staff.id  # waiting on the reader
    status = w.client.get(f"{API}/pos/payments/{payment.id}", headers=w.h).json()
    assert status["status"] == "REQUIRES_ACTION"
    _handle_payment_succeeded(w.db, stripe.StripeObject.construct_from({"id": payment.provider_intent_id, "amount_details": {"tip": {"amount": 300}}}, "sk"))
    w.db.refresh(payment)
    assert payment.status == PaymentStatus.COMPLETED and payment.tip_amount == Decimal("3.00")
    assert w.db.get(Order, oid).status == OrderStatus.CONFIRMED
    assert w.client.get(f"{API}/pos/payments/{payment.id}", headers=w.h).json()["tip_amount"] == "3.00"


def test_a_reader_that_isnt_ours_is_refused(live):
    oid = counter(live)
    assert live.client.post(f"{API}/pos/orders/{oid}/pay-reader", headers=live.h, json={"reader_id": "tmr_someone_elses"}).status_code == 404


def test_a_busy_reader_fails_the_attempt_cleanly(live):
    w = live
    oid = counter(w)
    FakeStripe.reader_error = True
    r = w.client.post(f"{API}/pos/orders/{oid}/pay-reader", headers=w.h, json={"reader_id": "tmr_1"})
    assert r.status_code == 400 and "busy" in r.json()["detail"]
    assert w.db.query(Payment).filter_by(order_id=oid).one().status == PaymentStatus.FAILED
    assert any(c[0] == "pi_cancel" for c in FakeStripe.calls)
    FakeStripe.reader_error = False  # and the sale can simply be tried again
    assert w.client.post(f"{API}/pos/orders/{oid}/pay-reader", headers=w.h, json={"reader_id": "tmr_1"}).status_code == 200


def test_a_tab_part_payment_can_go_to_the_reader(live):
    w = live
    sid = seat_with_round(w, qty=2)
    r = w.client.post(f"{API}/pos/table-sessions/{sid}/pay-reader", headers=w.h, json={"reader_id": "tmr_1", "split": {"mode": "EVEN", "parts_remaining": 2}})
    assert r.status_code == 200, r.text
    payment = w.db.get(Payment, r.json()["payment_id"])
    assert payment.amount == Decimal("13.20") and payment.status == PaymentStatus.REQUIRES_ACTION
    # While the reader is taking it, a second attempt is held off.
    assert w.client.post(f"{API}/pos/table-sessions/{sid}/pay-reader", headers=w.h, json={"reader_id": "tmr_1"}).status_code == 400
    _handle_payment_succeeded(w.db, stripe.StripeObject.construct_from({"id": payment.provider_intent_id}, "sk"))
    assert w.db.get(TableSession, sid).state == "OPEN" and w.client.get(f"{API}/pos/table-sessions/{sid}", headers=w.h).json()["balance"] == "13.20"


def test_the_reader_giving_up_frees_the_payment(live):
    w = live
    oid = counter(w)
    payment = w.db.get(Payment, w.client.post(f"{API}/pos/orders/{oid}/pay-reader", headers=w.h, json={"reader_id": "tmr_1"}).json()["payment_id"])
    event = stripe.StripeObject.construct_from(
        {"id": "tmr_1", "action": {"type": "process_payment_intent", "failure_message": "Card declined", "process_payment_intent": {"payment_intent": payment.provider_intent_id}}}, "sk",
    )
    _handle_reader_action_failed(w.db, event)
    w.db.refresh(payment)
    assert payment.status == PaymentStatus.FAILED and payment.failure_message == "Card declined"


def test_cancelling_the_reader_frees_my_unfinished_payments(live):
    w = live
    oid = counter(w)
    payment = w.db.get(Payment, w.client.post(f"{API}/pos/orders/{oid}/pay-reader", headers=w.h, json={"reader_id": "tmr_1"}).json()["payment_id"])
    assert w.client.post(f"{API}/pos/readers/tmr_1/cancel", headers=w.h).status_code == 204
    w.db.refresh(payment)
    assert payment.status == PaymentStatus.FAILED
    assert any(c[0] == "cancel_action" for c in FakeStripe.calls)


def test_a_pay_later_order_goes_back_to_waiting_when_the_reader_fails(live):
    w = live
    FeatureService(w.db).set(w.a.rid, "pay_later", True, None, actor_label="test")
    oid = counter(w)
    order = w.db.get(Order, oid)
    order.pay_later, order.status = True, OrderStatus.CONFIRMED
    w.db.commit()
    w.db.query(Payment).filter_by(order_id=oid).delete()
    w.db.add(Payment(order_id=oid, restaurant_id=w.a.rid, amount=order.total, status=PaymentStatus.PENDING, payment_method="CASH", provider="MANUAL"))
    w.db.commit()
    r = w.client.post(f"{API}/pos/orders/{oid}/pay-reader", headers=w.h, json={"reader_id": "tmr_1"})
    assert r.status_code == 200, r.text
    payment = w.db.get(Payment, r.json()["payment_id"])
    _handle_reader_action_failed(w.db, stripe.StripeObject.construct_from({"id": "tmr_1", "action": {"failure_message": "Timed out", "process_payment_intent": {"payment_intent": payment.provider_intent_id}}}, "sk"))
    w.db.refresh(payment)
    assert payment.status == PaymentStatus.PENDING and payment.provider_intent_id is None  # still owes the money, ready to be tried again
