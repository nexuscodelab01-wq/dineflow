"""Per-employee report: cash/card takings from Payment.staff_user_id, hours from TimeEntry — admin-only,
since individual earnings/hours are more sensitive than the aggregate analytics any staff member can see.
A guest's own online order (no staff involved) must never show up here."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.db.session import get_db
from app.main import app
from app.models.restaurant_user import RestaurantUser
from app.models.time_entry import TimeEntry
from app.services.feature_service import FeatureService
from tests.conftest import override_get_db
from tests.tenants import header, make_tenant, place_order

API = "/api/v1"


@pytest.fixture
def world(client, db):
    app.dependency_overrides[get_db] = override_get_db(db)
    a = make_tenant(db, "Alpha")
    FeatureService(db).set(a.rid, "pos", True, None, actor_label="test")
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


def test_employee_report_splits_cash_and_card_and_includes_hours(world):
    w = world
    staff_headers = pos_session(w, w.a, w.a.staff)

    cash_order = w.client.post(f"{API}/pos/orders", headers=staff_headers, json={"items": [{"menu_item_id": w.a.item.id, "quantity": 1, "modifier_option_ids": []}]})
    w.client.post(f"{API}/pos/orders/{cash_order.json()['order_id']}/pay-cash", headers=staff_headers)
    card_order = w.client.post(f"{API}/pos/orders", headers=staff_headers, json={"items": [{"menu_item_id": w.a.item.id, "quantity": 1, "modifier_option_ids": []}]})
    w.client.post(f"{API}/pos/orders/{card_order.json()['order_id']}/pay-card", headers=staff_headers)

    now = datetime.now(UTC)
    w.db.add(TimeEntry(restaurant_id=w.a.rid, user_id=w.a.staff.id, clock_in_at=now - timedelta(hours=2), clock_out_at=now))
    w.db.commit()

    # A guest's own online order — no staff involved, must never appear in this report.
    place_order(w.client, w.a)

    r = w.client.get(f"{API}/admin/analytics/employees", params={"restaurant_id": w.a.rid, "range": "today"}, headers=header(w.a.admin))
    assert r.status_code == 200, r.text
    rows = r.json()
    assert len(rows) == 1
    row = rows[0]
    assert row["user_id"] == w.a.staff.id
    expected_each = (Decimal("12.00") * Decimal("1.10")).quantize(Decimal("0.01"))
    assert Decimal(row["cash_total"]) == expected_each
    assert Decimal(row["card_total"]) == expected_each
    assert row["order_count"] == 2
    assert Decimal(row["hours_worked"]) == Decimal("2.00")
    expected_rate = ((expected_each * 2) / Decimal("2.00")).quantize(Decimal("0.01"))
    assert Decimal(row["sales_per_labour_hour"]) == expected_rate


def test_employee_report_requires_admin(world):
    w = world
    r = w.client.get(f"{API}/admin/analytics/employees", params={"restaurant_id": w.a.rid, "range": "today"}, headers=header(w.a.staff))
    assert r.status_code == 403


def test_employee_with_no_closed_time_entry_has_no_hours_but_still_appears(world):
    w = world
    staff_headers = pos_session(w, w.a, w.a.staff)
    order = w.client.post(f"{API}/pos/orders", headers=staff_headers, json={"items": [{"menu_item_id": w.a.item.id, "quantity": 1, "modifier_option_ids": []}]})
    w.client.post(f"{API}/pos/orders/{order.json()['order_id']}/pay-cash", headers=staff_headers)

    r = w.client.get(f"{API}/admin/analytics/employees", params={"restaurant_id": w.a.rid, "range": "today"}, headers=header(w.a.admin))
    assert r.status_code == 200, r.text
    row = r.json()[0]
    assert Decimal(row["hours_worked"]) == Decimal("0.00")
    assert row["sales_per_labour_hour"] is None
