"""Kitchen v2: stations, item-level bump/recall keeping the order's status in step, and 86 (sold out) live."""

from decimal import Decimal

import pytest

from app.models.menu_item import MenuItem
from app.models.order import Order
from tests.test_admin_management import url, world  # noqa: F401  (world is a fixture)
from tests.test_live_status import announced  # noqa: F401  (fixture)


@pytest.fixture
def bar_item(world):
    w = world
    item = MenuItem(restaurant_id=w.a.id, category_id=w.cat.id, name="Lemonade", price=Decimal("4.00"), is_available=True, station="BAR")
    w.db.add(item)
    w.db.flush()
    return item


def order_two(w, bar):
    r = w.client.post("/api/v1/orders", headers=w.customer, json={
        "restaurant_id": w.a.id, "order_type": "PICKUP", "customer_name": "Cara", "customer_email": "am-cust@demo.com",
        "items": [{"menu_item_id": w.item.id, "quantity": 1, "modifier_option_ids": []},
                  {"menu_item_id": bar.id, "quantity": 2, "modifier_option_ids": []}]})
    assert r.status_code == 201, r.text
    return w.db.get(Order, r.json()["id"])


def kitchen(w, method, path, who=None, restaurant=None, query=None, **kw):
    return getattr(w.client, method)(url(w, path, restaurant, **(query or {})), headers=who or w.staff, **kw)


# ------------------------------------------------------------------ stations

def test_dishes_have_a_station_that_defaults_to_the_kitchen(world):
    w = world
    made = kitchen(w, "post", "/menu", w.admin, json={"restaurant_id": w.a.id, "category_id": w.cat.id, "name": "Mojito", "price": "8.00", "station": "BAR"})
    assert made.status_code == 201 and made.json()["station"] == "BAR"
    plain = kitchen(w, "post", "/menu", w.admin, json={"restaurant_id": w.a.id, "category_id": w.cat.id, "name": "Soup", "price": "6.00"})
    assert plain.json()["station"] == "KITCHEN"
    assert kitchen(w, "put", f"/menu/{plain.json()['id']}", w.admin, json={"station": "DESSERT"}).json()["station"] == "DESSERT"
    bad = kitchen(w, "put", f"/menu/{plain.json()['id']}", w.admin, json={"station": "GARAGE"})
    assert bad.status_code == 422


def test_an_order_line_remembers_the_station_it_was_ordered_for(world, bar_item):
    w = world
    order = order_two(w, bar_item)
    assert {(i.item_name, i.station, i.status) for i in order.items} == {("Burger", "KITCHEN", "NEW"), ("Lemonade", "BAR", "NEW")}
    bar_item.station = "KITCHEN"                                        # the dish moves later…
    w.db.flush()
    w.db.refresh(order)
    assert {i.station for i in order.items} == {"KITCHEN", "BAR"}       # …the ticket already on a screen does not


def test_the_board_carries_each_dishs_station_and_status(world, bar_item):
    w = world
    order = order_two(w, bar_item)
    board = kitchen(w, "get", "/kitchen").json()
    ticket = next(o for col in board.values() for o in col if o["id"] == order.id)
    assert sorted((i["item_name"], i["station"], i["status"]) for i in ticket["items"]) == [("Burger", "KITCHEN", "NEW"), ("Lemonade", "BAR", "NEW")]


# ------------------------------------------------------------------ bump / recall

def test_bumping_dishes_moves_the_order_through_preparing_to_ready_and_recall_reverses_it(world, bar_item, announced):
    w = world
    order = order_two(w, bar_item)
    burger, lemonade = sorted(order.items, key=lambda i: i.item_name)
    assert order.status.value == "CONFIRMED"
    announced.clear()

    assert kitchen(w, "post", f"/kitchen/items/{lemonade.id}/bump").status_code == 204
    w.db.refresh(order)
    assert order.status.value == "PREPARING" and lemonade.status == "READY" and lemonade.ready_at is not None
    assert any(e[1] == "order.status" and e[2]["status"] == "PREPARING" for e in announced)
    assert any(t == f"order:{order.id}" for t, *_ in announced)                 # the customer hears about it too

    assert kitchen(w, "post", f"/kitchen/items/{burger.id}/bump").status_code == 204
    w.db.refresh(order)
    assert order.status.value == "READY"

    assert kitchen(w, "post", f"/kitchen/items/{burger.id}/recall").status_code == 204
    w.db.refresh(order)
    assert order.status.value == "PREPARING" and burger.status == "NEW" and burger.ready_at is None
    assert [h.new_status.value for h in order.status_history][-3:] == ["PREPARING", "READY", "PREPARING"]


def test_bumping_the_same_dish_twice_is_harmless(world, bar_item):
    w = world
    order = order_two(w, bar_item)
    bar = next(i for i in order.items if i.station == "BAR")
    for _ in range(2):
        assert kitchen(w, "post", f"/kitchen/items/{bar.id}/bump").status_code == 204
    w.db.refresh(order)
    assert order.status.value == "PREPARING"


def test_bumping_a_ticket_can_be_limited_to_one_station(world, bar_item):
    w = world
    order = order_two(w, bar_item)
    assert kitchen(w, "post", f"/kitchen/orders/{order.id}/bump", query={"station": "BAR"}).status_code == 204
    w.db.refresh(order)
    assert {i.item_name: i.status for i in order.items} == {"Burger": "NEW", "Lemonade": "READY"} and order.status.value == "PREPARING"
    assert kitchen(w, "post", f"/kitchen/orders/{order.id}/bump", query={"station": "NOPE"}).status_code == 400
    assert kitchen(w, "post", f"/kitchen/orders/{order.id}/bump").status_code == 204
    w.db.refresh(order)
    assert order.status.value == "READY" and all(i.status == "READY" for i in order.items)


def test_marking_the_whole_order_ready_by_hand_finishes_its_dishes(world, bar_item):
    w = world
    order = order_two(w, bar_item)
    kitchen(w, "patch", f"/orders/{order.id}/status", json={"status": "PREPARING"})
    kitchen(w, "patch", f"/orders/{order.id}/status", json={"status": "READY"})
    w.db.refresh(order)
    assert all(i.status == "READY" for i in order.items)


def test_only_this_restaurants_staff_can_bump_and_finished_orders_are_left_alone(world, bar_item):
    w = world
    order = order_two(w, bar_item)
    line = order.items[0]
    assert kitchen(w, "post", f"/kitchen/items/{line.id}/bump", w.customer).status_code == 403
    assert kitchen(w, "post", f"/kitchen/items/{line.id}/bump", w.admin_b, restaurant=w.b).status_code == 404     # Bravo naming its own restaurant
    assert kitchen(w, "post", f"/kitchen/items/{line.id}/bump", w.admin_b).status_code == 403                    # or naming Alpha's
    assert kitchen(w, "post", "/kitchen/items/999999/bump").status_code == 404
    kitchen(w, "patch", f"/orders/{order.id}/status", json={"status": "PREPARING"})
    kitchen(w, "patch", f"/orders/{order.id}/status", json={"status": "READY"})
    kitchen(w, "patch", f"/orders/{order.id}/status", json={"status": "COMPLETED"})
    assert kitchen(w, "post", f"/kitchen/items/{line.id}/recall").status_code == 400                                # off the screen already


# ------------------------------------------------------------------ 86

def test_staff_can_86_a_dish_and_it_disappears_from_menus_and_ordering(world, announced):
    w = world
    assert kitchen(w, "post", f"/menu/{w.item.id}/sold-out", json={"sold_out": True}).json() == {"id": w.item.id, "is_available": False}
    assert any(e[1] == "menu.changed" and e[2]["menu_item_id"] == w.item.id for e in announced)
    listed = w.client.get(f"/api/v1/menu?restaurant_id={w.a.id}").json()["items"]
    assert w.item.id not in [i["id"] for i in listed]
    refused = w.client.post("/api/v1/orders", headers=w.customer, json={
        "restaurant_id": w.a.id, "order_type": "PICKUP", "customer_name": "C", "customer_email": "am-cust@demo.com",
        "items": [{"menu_item_id": w.item.id, "quantity": 1, "modifier_option_ids": []}]})
    assert refused.status_code == 400 and "unavailable" in refused.json()["detail"]
    assert kitchen(w, "post", f"/menu/{w.item.id}/sold-out", json={"sold_out": False}).json()["is_available"] is True
    assert w.item.id in [i["id"] for i in w.client.get(f"/api/v1/menu?restaurant_id={w.a.id}").json()["items"]]


def test_86_is_limited_to_the_dishs_own_restaurant_and_to_staff(world):
    w = world
    assert kitchen(w, "post", f"/menu/{w.item.id}/sold-out", w.customer, json={"sold_out": True}).status_code == 403
    assert kitchen(w, "post", f"/menu/{w.item.id}/sold-out", w.admin_b, restaurant=w.b, json={"sold_out": True}).status_code == 404
    assert kitchen(w, "post", f"/menu/{w.item.id}/sold-out", w.admin_b, json={"sold_out": True}).status_code == 403
    w.db.refresh(w.item)
    assert w.item.is_available is True
