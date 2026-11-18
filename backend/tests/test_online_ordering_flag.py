"""online_ordering: a restaurant that only wants its menu shown. Off = no customer orders, quotes or collection slots;
the kitchen and order list stay available only while some OTHER ordering channel (POS, table QR) is on."""

import pytest

from app.db.session import get_db
from app.main import app
from app.services.feature_service import FeatureService
from tests.conftest import override_get_db
from tests.tenants import header, make_tenant, place_order

API = "/api/v1"


@pytest.fixture
def world(client, db):
    app.dependency_overrides[get_db] = override_get_db(db)
    a = make_tenant(db, "Alpha")
    yield type("W", (), {"client": client, "db": db, "a": a})
    app.dependency_overrides.clear()


def set_flag(w, key, on):
    FeatureService(w.db).set(w.a.rid, key, on, None, actor_label="test")
    w.db.commit()


def quote(w):
    return w.client.post(f"{API}/orders/quote", headers=header(w.a.customer), json={
        "restaurant_id": w.a.rid, "order_type": "PICKUP", "items": [{"menu_item_id": w.a.item.id, "quantity": 1, "modifier_option_ids": []}],
    })


def admin_get(w, path):
    return w.client.get(f"{API}/admin/{path}", params={"restaurant_id": w.a.rid}, headers=header(w.a.admin))


def test_it_is_on_by_default_so_existing_restaurants_keep_ordering(world):
    w = world
    assert place_order(w.client, w.a).status_code == 201
    assert quote(w).status_code == 200
    # What the site's own /tenant call reports: the flag is part of the restaurant's resolved feature set, and ON.
    assert FeatureService(w.db).resolve(w.a.rid)["online_ordering"] is True


def test_turned_off_customers_cannot_order_or_get_a_quote(world):
    w = world
    set_flag(w, "online_ordering", False)
    assert place_order(w.client, w.a).status_code == 403
    assert quote(w).status_code == 403


def test_turned_off_there_are_no_collection_slots_either(world):
    w = world
    set_flag(w, "scheduled_orders", True)
    assert w.client.get(f"{API}/restaurants/{w.a.slug}/pickup-slots").status_code == 200
    set_flag(w, "online_ordering", False)
    assert w.client.get(f"{API}/restaurants/{w.a.slug}/pickup-slots").status_code == 403


def test_the_menu_stays_visible(world):
    w = world
    set_flag(w, "online_ordering", False)
    r = w.client.get(f"{API}/menu", params={"restaurant_id": w.a.rid})
    assert r.status_code == 200 and r.json()["items"]


def test_with_every_ordering_channel_off_the_kitchen_and_order_list_are_closed(world):
    w = world
    set_flag(w, "online_ordering", False)
    for path in ("orders", "kitchen"):
        assert admin_get(w, path).status_code == 403, path


@pytest.mark.parametrize("other_channel", ["pos", "qr_table_ordering"])
def test_another_channel_keeps_the_kitchen_and_orders_open(world, other_channel):
    w = world
    set_flag(w, "online_ordering", False)
    set_flag(w, other_channel, True)
    assert admin_get(w, "kitchen").status_code == 200
    assert admin_get(w, "orders").status_code == 200


def test_online_ordering_alone_keeps_them_open(world):
    assert admin_get(world, "kitchen").status_code == 200  # the default state


def test_the_flag_is_per_restaurant(world):
    w = world
    b = make_tenant(w.db, "Bravo")
    set_flag(w, "online_ordering", False)
    assert place_order(w.client, b).status_code == 201
    assert place_order(w.client, w.a).status_code == 403


def test_turned_off_a_customers_past_orders_are_not_available_either(world):
    w = world
    placed = place_order(w.client, w.a)
    assert placed.status_code == 201
    order_id = placed.json()["id"]
    assert w.client.get(f"{API}/orders", headers=header(w.a.customer)).status_code == 200
    assert w.client.get(f"{API}/orders/{order_id}", headers=header(w.a.customer)).status_code == 200
    set_flag(w, "online_ordering", False)
    assert w.client.get(f"{API}/orders", headers=header(w.a.customer)).status_code == 403
    assert w.client.get(f"{API}/orders/{order_id}", headers=header(w.a.customer)).status_code == 403


def register(w, email):
    return w.client.post(f"{API}/auth/register", json={
        "restaurant_id": w.a.rid, "email": email, "password": "Str0ng-Passw0rd!", "first_name": "Sam", "last_name": "Guest",
    })


def test_menu_only_site_takes_no_customer_sign_ups(world):
    w = world
    assert register(w, "ok1@example.com").status_code == 201  # defaults: ordering on
    for key in ("online_ordering", "reservations", "loyalty", "reviews"):
        set_flag(w, key, False)
    assert register(w, "no@example.com").status_code == 403


def test_a_site_with_only_reviews_still_takes_sign_ups(world):
    w = world
    for key in ("online_ordering", "reservations", "loyalty"):
        set_flag(w, key, False)
    set_flag(w, "reviews", True)
    assert register(w, "rev@example.com").status_code == 201


def test_staff_can_still_sign_in_on_a_menu_only_site(world):
    w = world
    for key in ("online_ordering", "reservations", "loyalty", "reviews"):
        set_flag(w, key, False)
    r = w.client.post(f"{API}/auth/login", json={"email": w.a.admin.email, "password": "Test1234!", "restaurant_id": w.a.rid})
    assert r.status_code == 200
