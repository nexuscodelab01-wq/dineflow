"""Admin device pairing: pair, list, revoke — and that a revoked device's token dies immediately."""

import pytest

from app.db.session import get_db
from app.main import app
from app.models.audit_log import AuditLog
from app.models.device import Device
from tests.conftest import override_get_db
from tests.tenants import header, make_tenant

API = "/api/v1"


@pytest.fixture
def world(client, db):
    app.dependency_overrides[get_db] = override_get_db(db)
    yield type("W", (), {"client": client, "db": db, "a": make_tenant(db, "Alpha"), "b": make_tenant(db, "Bravo")})
    app.dependency_overrides.clear()


def test_an_admin_can_pair_list_and_revoke_a_device(world):
    w = world
    paired = w.client.post(f"{API}/admin/devices", params={"restaurant_id": w.a.rid}, headers=header(w.a.admin), json={"label": "Front counter"})
    assert paired.status_code == 201, paired.text
    body = paired.json()
    assert body["label"] == "Front counter" and body["device_token"]

    listing = w.client.get(f"{API}/admin/devices", params={"restaurant_id": w.a.rid}, headers=header(w.a.admin)).json()
    assert len(listing) == 1 and listing[0]["label"] == "Front counter" and listing[0]["revoked_at"] is None

    revoked = w.client.post(f"{API}/admin/devices/{body['device_id']}/revoke", params={"restaurant_id": w.a.rid}, headers=header(w.a.admin))
    assert revoked.status_code == 204

    after = w.client.get(f"{API}/admin/devices", params={"restaurant_id": w.a.rid}, headers=header(w.a.admin)).json()
    assert after[0]["revoked_at"] is not None


def test_a_revoked_devices_token_is_rejected_immediately(world):
    w = world
    paired = w.client.post(f"{API}/admin/devices", params={"restaurant_id": w.a.rid}, headers=header(w.a.admin), json={"label": "Till"})
    device_token = paired.json()["device_token"]
    device_id = paired.json()["device_id"]

    ok = w.client.get(f"{API}/pos/table-sessions/open", headers={"Authorization": f"Bearer {device_token}"})
    assert ok.status_code in (200, 403)  # 403 only if the "pos" flag is off — either way, not revoked-rejected

    w.client.post(f"{API}/admin/devices/{device_id}/revoke", params={"restaurant_id": w.a.rid}, headers=header(w.a.admin))

    after = w.client.get(f"{API}/pos/table-sessions/open", headers={"Authorization": f"Bearer {device_token}"})
    assert after.status_code == 401


def test_staff_cannot_pair_or_revoke_devices(world):
    w = world
    assert w.client.post(f"{API}/admin/devices", params={"restaurant_id": w.a.rid}, headers=header(w.a.staff), json={"label": "x"}).status_code == 403
    assert w.client.get(f"{API}/admin/devices", params={"restaurant_id": w.a.rid}, headers=header(w.a.staff)).status_code == 403


def test_an_admin_cannot_revoke_another_restaurants_device(world):
    w = world
    paired = w.client.post(f"{API}/admin/devices", params={"restaurant_id": w.a.rid}, headers=header(w.a.admin), json={"label": "Till"})
    device_id = paired.json()["device_id"]

    r = w.client.post(f"{API}/admin/devices/{device_id}/revoke", params={"restaurant_id": w.b.rid}, headers=header(w.b.admin))
    assert r.status_code == 404
    assert w.db.get(Device, device_id).revoked_at is None


def test_pairing_and_revoking_are_audited(world):
    w = world
    paired = w.client.post(f"{API}/admin/devices", params={"restaurant_id": w.a.rid}, headers=header(w.a.admin), json={"label": "Till"})
    device_id = paired.json()["device_id"]
    w.client.post(f"{API}/admin/devices/{device_id}/revoke", params={"restaurant_id": w.a.rid}, headers=header(w.a.admin))

    rows = w.db.query(AuditLog).filter_by(restaurant_id=w.a.rid).order_by(AuditLog.id).all()
    actions = [r.action for r in rows]
    assert "device.paired" in actions and "device.revoked" in actions
