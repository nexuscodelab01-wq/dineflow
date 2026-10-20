"""Card tender from the POS (Stripe Terminal) — flag-gated, confirms a counter order or closes a
table's tab exactly like cash does once the (mock) provider settles synchronously. The connection-token
endpoint refuses outright under PAYMENT_PROVIDER=mock, since there's no real Terminal SDK session to
authenticate without Stripe."""

import pytest

from app.db.session import get_db
from app.main import app
from app.models.enums import OrderStatus, PaymentStatus, TableStatus
from app.models.order import Order
from app.models.payment import Payment
from app.models.restaurant_user import RestaurantUser
from app.models.table_session import OPEN, TableSession
from app.services.feature_service import FeatureService
from tests.conftest import override_get_db
from tests.tenants import header, make_tenant

API = "/api/v1"


@pytest.fixture
def world(client, db):
    app.dependency_overrides[get_db] = override_get_db(db)
    a = make_tenant(db, "Alpha")
    FeatureService(db).set(a.rid, "pos", True, None, actor_label="test")
    FeatureService(db).set(a.rid, "qr_table_ordering", True, None, actor_label="test")
    a.table.status = TableStatus.OCCUPIED
    db.flush()
    yield type("W", (), {"client": client, "db": db, "a": a})
    app.dependency_overrides.clear()


def membership_id(w, tenant, user):
    return w.db.query(RestaurantUser).filter_by(restaurant_id=tenant.rid, user_id=user.id).one().id


def pos_session(w, tenant, user, pin="1234"):
    mid = membership_id(w, tenant, user)
    r = w.client.post(f"{API}/admin/devices/staff/{mid}/pin", params={"restaurant_id": tenant.rid}, headers=header(tenant.admin), json={"pin": pin})
    assert r.status_code == 204
    paired = w.client.post(f"{API}/admin/devices", params={"restaurant_id": tenant.rid}, headers=header(tenant.admin), json={"label": "Till"})
    device_token = paired.json()["device_token"]
    login = w.client.post(f"{API}/pos/auth/pin-login", headers={"Authorization": f"Bearer {device_token}"}, json={"pin": pin})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['pos_session_token']}"}


def open_session(w, t):
    r = w.client.post(f"{API}/t/{t.table.qr_token}/join", params={"restaurant_id": t.rid}, json={"name": "Guest"})
    assert r.status_code == 200, r.text
    return w.db.query(TableSession).filter_by(table_id=t.table.id, state=OPEN).one().id


def test_card_tender_confirms_the_order_under_mock(world):
    w = world
    staff_headers = pos_session(w, w.a, w.a.staff)
    created = w.client.post(f"{API}/pos/orders", headers=staff_headers, json={"items": [{"menu_item_id": w.a.item.id, "quantity": 1, "modifier_option_ids": []}]})
    order_id = created.json()["order_id"]
    assert w.db.get(Order, order_id).status == OrderStatus.PENDING

    r = w.client.post(f"{API}/pos/orders/{order_id}/pay-card", headers=staff_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "CONFIRMED"
    assert body["client_secret"] is None

    order = w.db.get(Order, order_id)
    assert order.status == OrderStatus.CONFIRMED
    payment = w.db.query(Payment).filter_by(order_id=order_id).one()
    assert payment.status == PaymentStatus.COMPLETED
    assert payment.payment_method.value == "CARD"
    assert payment.provider == "MOCK"
    assert payment.provider_intent_id.startswith("mock_")
    assert payment.staff_user_id == w.a.staff.id


def test_card_tender_refuses_an_already_paid_order(world):
    w = world
    staff_headers = pos_session(w, w.a, w.a.staff)
    created = w.client.post(f"{API}/pos/orders", headers=staff_headers, json={"items": [{"menu_item_id": w.a.item.id, "quantity": 1, "modifier_option_ids": []}]})
    order_id = created.json()["order_id"]
    w.client.post(f"{API}/pos/orders/{order_id}/pay-cash", headers=staff_headers)

    r = w.client.post(f"{API}/pos/orders/{order_id}/pay-card", headers=staff_headers)
    assert r.status_code == 400


def test_card_tender_requires_the_pos_flag(world):
    w = world
    staff_headers = pos_session(w, w.a, w.a.staff)
    created = w.client.post(f"{API}/pos/orders", headers=staff_headers, json={"items": [{"menu_item_id": w.a.item.id, "quantity": 1, "modifier_option_ids": []}]})
    order_id = created.json()["order_id"]
    FeatureService(w.db).set(w.a.rid, "pos", None, None, actor_label="test")  # back to default (off)

    r = w.client.post(f"{API}/pos/orders/{order_id}/pay-card", headers=staff_headers)
    assert r.status_code == 403


def test_connection_token_is_503_under_mock(world):
    w = world
    staff_headers = pos_session(w, w.a, w.a.staff)

    r = w.client.post(f"{API}/pos/terminal/connection-token", headers=staff_headers)
    assert r.status_code == 503


def test_table_session_card_tender_closes_the_tab_under_mock(world):
    w = world
    session_id = open_session(w, w.a)
    staff_headers = pos_session(w, w.a, w.a.staff)
    order = w.client.post(
        f"{API}/pos/table-sessions/{session_id}/orders", headers=staff_headers,
        json={"items": [{"menu_item_id": w.a.item.id, "quantity": 1, "modifier_option_ids": []}]},
    )
    assert order.status_code == 200, order.text

    r = w.client.post(f"{API}/pos/table-sessions/{session_id}/pay-card", headers=staff_headers)
    assert r.status_code == 200, r.text
    assert r.json()["closed"] is True

    session = w.db.get(TableSession, session_id)
    assert session.state != OPEN
    payment = w.db.query(Payment).filter_by(table_session_id=session_id).one()
    assert payment.status == PaymentStatus.COMPLETED
    assert payment.payment_method.value == "CARD"
    assert payment.staff_user_id == w.a.staff.id


def test_table_session_cash_tender_closes_the_tab_and_stamps_shift_and_staff(world):
    """The pay-cash route for table tabs was entirely missing until this milestone — cash could only be
    settled via the web admin, which bypassed device_id/shift_id stamping. This pins down the fix."""
    w = world
    session_id = open_session(w, w.a)
    staff_headers = pos_session(w, w.a, w.a.staff)
    order = w.client.post(
        f"{API}/pos/table-sessions/{session_id}/orders", headers=staff_headers,
        json={"items": [{"menu_item_id": w.a.item.id, "quantity": 1, "modifier_option_ids": []}]},
    )
    assert order.status_code == 200, order.text
    shift = w.client.post(f"{API}/pos/shifts/open", headers=staff_headers, json={"starting_float": "50.00"})
    assert shift.status_code == 201, shift.text

    r = w.client.post(f"{API}/pos/table-sessions/{session_id}/pay-cash", headers=staff_headers)
    assert r.status_code == 204, r.text

    session = w.db.get(TableSession, session_id)
    assert session.state != OPEN
    payment = w.db.query(Payment).filter_by(table_session_id=session_id).one()
    assert payment.status == PaymentStatus.COMPLETED
    assert payment.payment_method.value == "CASH"
    assert payment.provider == "MANUAL"
    assert payment.staff_user_id == w.a.staff.id
    assert payment.shift_id == shift.json()["shift_id"]
