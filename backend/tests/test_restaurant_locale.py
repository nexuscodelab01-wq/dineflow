"""Country + currency: settable per restaurant (US/Canada), locked once Stripe is connected, and fed to the POS."""

from decimal import Decimal

import pytest

from app.core.locale import format_money
from app.db.session import get_db
from app.main import app
from app.models.restaurant import Restaurant
from app.services.feature_service import FeatureService
from app.services.tenant_provisioning import provision_tenant
from tests.conftest import override_get_db
from tests.tenants import header, make_tenant

API = "/api/v1"


@pytest.fixture
def world(client, db):
    app.dependency_overrides[get_db] = override_get_db(db)
    a = make_tenant(db, "Alpha")
    yield type("W", (), {"client": client, "db": db, "a": a})
    app.dependency_overrides.clear()


def patch(w, **body):
    return w.client.patch(f"{API}/admin/settings", params={"restaurant_id": w.a.rid}, headers=header(w.a.admin), json=body)


def test_a_new_restaurant_is_us_dollars(world):
    r = world.client.get(f"{API}/admin/settings", params={"restaurant_id": world.a.rid}, headers=header(world.a.admin)).json()
    assert (r["country"], r["currency"]) == ("US", "usd")


def test_country_and_currency_can_be_set_to_canada(world):
    r = patch(world, country="ca", currency="CAD")
    assert r.status_code == 200, r.text
    assert (r.json()["country"], r.json()["currency"]) == ("CA", "cad")


@pytest.mark.parametrize("body", [{"country": "FR"}, {"currency": "eur"}, {"currency": "jpy"}])
def test_unsupported_values_are_refused(world, body):
    assert patch(world, **body).status_code == 422


def test_country_and_currency_lock_once_stripe_is_connected(world):
    w = world
    w.db.get(Restaurant, w.a.rid).stripe_account_id = "acct_123"
    w.db.commit()
    assert patch(w, country="CA").status_code == 400
    assert patch(w, currency="cad").status_code == 400
    # Re-sending the current value is not a change.
    assert patch(w, country="US", currency="usd", tax_rate="0.07").status_code == 200


def test_provisioning_a_canadian_restaurant_gets_cad(db):
    result = provision_tenant(db, name="Maple", slug="maple", owner_email="o@maple-demo.com", country="CA")
    r = db.get(Restaurant, result.restaurant_id)
    assert (r.country, r.currency) == ("CA", "cad")


def test_provisioning_refuses_an_unsupported_country(db):
    from app.core.exceptions import AppError

    with pytest.raises(AppError):
        provision_tenant(db, name="Paris", slug="paris", owner_email="o@paris-demo.com", country="FR")


def test_pin_login_tells_the_pos_the_currency(world):
    from app.models.restaurant_user import RestaurantUser

    w = world
    FeatureService(w.db).set(w.a.rid, "pos", True, None, actor_label="test")
    patch(w, country="CA", currency="cad")
    device = w.client.post(f"{API}/admin/devices", params={"restaurant_id": w.a.rid}, headers=header(w.a.admin), json={"label": "Till"}).json()
    mid = w.db.query(RestaurantUser).filter_by(restaurant_id=w.a.rid, user_id=w.a.staff.id).one().id
    w.client.post(f"{API}/admin/devices/staff/{mid}/pin", params={"restaurant_id": w.a.rid}, headers=header(w.a.admin), json={"pin": "1234"})
    login = w.client.post(f"{API}/pos/auth/pin-login", headers={"Authorization": f"Bearer {device['device_token']}"}, json={"pin": "1234"}).json()
    assert (login["currency"], login["country"]) == ("cad", "CA")


def test_format_money():
    assert format_money(Decimal("12.5"), "usd") == "$12.50"
    assert format_money(Decimal("12.5"), "cad") == "$12.50 CAD"
