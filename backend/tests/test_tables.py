"""Table management and floor-plan tests."""

from datetime import timedelta

from tests.test_reservation_flows import (  # noqa: F401  (world is a fixture)
    _admin_book,
    _book,
    _iso,
    _now,
    _table_status,
    world,
)


def _create(w, number="W1", capacity=2, **extra):
    return w.client.post(
        f"/api/v1/admin/tables?restaurant_id={w.rid}", headers=w.ah,
        json={"restaurant_id": w.rid, "table_number": number, "capacity": capacity, **extra},
    )


def _update(w, table_id, **fields):
    return w.client.put(f"/api/v1/admin/tables/{table_id}?restaurant_id={w.rid}", headers=w.ah, json=fields)


def _list(w, **params):
    return w.client.get("/api/v1/admin/tables", headers=w.ah, params={"restaurant_id": w.rid, **params}).json()


def test_create_table_with_zone_shape_and_position(world):
    w = world
    r = _create(w, "  W1 ", 4, zone="  Window ", shape="ROUND", pos_x=12.5, pos_y=30)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["table_number"] == "W1" and body["zone"] == "Window" and body["shape"] == "ROUND"
    assert (body["pos_x"], body["pos_y"], body["is_active"]) == (12.5, 30, True)

    assert _create(w, "W1", 2).status_code == 409                       # duplicate name
    assert _create(w, "   ", 2).status_code == 422                      # blank name
    assert _create(w, "X9", 2, shape="TRIANGLE").status_code == 422     # unknown shape
    assert _create(w, "X9", 2, pos_x=150).status_code == 422            # off the plan
    assert _create(w, "X9", 0).status_code == 422


def test_only_admins_manage_tables(world):
    w = world
    r = w.client.post(
        f"/api/v1/admin/tables?restaurant_id={w.rid}", headers=w.ch,
        json={"restaurant_id": w.rid, "table_number": "Z1", "capacity": 2},
    )
    assert r.status_code == 403


def test_rename_reshape_and_clear_zone(world):
    w = world
    assert _update(w, w.t1.id, table_number="Window 1", zone="Window", shape="RECT").status_code == 200
    row = next(t for t in _list(w) if t["id"] == w.t1.id)
    assert (row["table_number"], row["zone"], row["shape"]) == ("Window 1", "Window", "RECT")

    assert _update(w, w.t1.id, zone=None).json()["zone"] is None          # explicit null clears
    assert _update(w, w.t1.id, table_number="T2").status_code == 409       # name already used by another table
    assert _update(w, w.t1.id, table_number="Window 1").status_code == 200  # keeping own name is fine
    assert _update(w, w.t1.id, capacity=None).status_code == 400


def test_capacity_cannot_drop_below_a_booked_party(world):
    w = world
    big = w.client.post(
        f"/api/v1/admin/reservations?restaurant_id={w.rid}", headers=w.ah,
        json={"table_id": w.t3.id, "party_size": 5, "starts_at": _iso(_now() + timedelta(hours=8)), "guest_name": "Five"},
    )
    assert big.status_code == 201, big.text

    r = _update(w, w.t3.id, capacity=4)
    assert r.status_code == 409 and "Five" in r.json()["detail"]
    assert _update(w, w.t3.id, capacity=5).status_code == 200
    assert _update(w, w.t3.id, capacity=8).status_code == 200


def test_taking_a_table_out_of_service(world):
    w = world
    res = _admin_book(w, w.t2, _now() + timedelta(hours=3), name="Booked").json()

    blocked = _update(w, w.t2.id, is_active=False)
    assert blocked.status_code == 409 and "Booked" in blocked.json()["detail"]

    w.client.patch(f"/api/v1/admin/reservations/{res['id']}/status?restaurant_id={w.rid}", headers=w.ah, json={"status": "CANCELLED"})
    assert _update(w, w.t2.id, is_active=False).status_code == 200

    assert all(t["id"] != w.t2.id for t in _list(w))                                  # hidden by default…
    assert any(t["id"] == w.t2.id and t["is_active"] is False for t in _list(w, include_inactive=True))

    # …unbookable…
    assert _admin_book(w, w.t2, _now() + timedelta(hours=5), name="Nope").status_code == 400
    # …and absent from availability, for customers and staff.
    params = {"starts_at": _iso(_now() + timedelta(hours=5)), "party_size": 2}
    pub = w.client.get(f"/api/v1/restaurants/{w.restaurant.slug}/reservations/availability", params=params).json()
    assert w.t2.id not in [t["id"] for t in pub["tables"]] and w.t2.id not in [t["id"] for t in pub["floor"]]
    adm = w.client.get("/api/v1/admin/reservations/availability", headers=w.ah, params={"restaurant_id": w.rid, **params}).json()
    assert w.t2.id not in [t["id"] for t in adm["tables"]]

    # Bring it back.
    assert _update(w, w.t2.id, is_active=True).status_code == 200
    assert _admin_book(w, w.t2, _now() + timedelta(hours=5), name="Back").status_code == 201


def test_delete_only_tables_without_history(world):
    w = world
    fresh = _create(w, "Temp", 2).json()
    assert w.client.delete(f"/api/v1/admin/tables/{fresh['id']}?restaurant_id={w.rid}", headers=w.ah).status_code == 204
    assert all(t["id"] != fresh["id"] for t in _list(w, include_inactive=True))

    res = _admin_book(w, w.t1, _now() + timedelta(hours=3)).json()
    w.client.patch(f"/api/v1/admin/reservations/{res['id']}/status?restaurant_id={w.rid}", headers=w.ah, json={"status": "CANCELLED"})
    r = w.client.delete(f"/api/v1/admin/tables/{w.t1.id}?restaurant_id={w.rid}", headers=w.ah)
    assert r.status_code == 409 and "out of service" in r.json()["detail"]
    assert _update(w, w.t1.id, is_active=False).status_code == 200      # the supported way to retire it


def test_save_layout_in_bulk(world):
    w = world
    r = w.client.put(
        f"/api/v1/admin/tables/layout?restaurant_id={w.rid}", headers=w.ah,
        json={"items": [{"id": w.t1.id, "pos_x": 10, "pos_y": 20}, {"id": w.t2.id, "pos_x": 55.5, "pos_y": 70}]},
    )
    assert r.status_code == 200, r.text
    rows = {t["id"]: t for t in _list(w)}
    assert (rows[w.t1.id]["pos_x"], rows[w.t1.id]["pos_y"]) == (10, 20)
    assert (rows[w.t2.id]["pos_x"], rows[w.t2.id]["pos_y"]) == (55.5, 70)

    bad = w.client.put(f"/api/v1/admin/tables/layout?restaurant_id={w.rid}", headers=w.ah,
                       json={"items": [{"id": w.t1.id, "pos_x": 101, "pos_y": 0}]})
    assert bad.status_code == 422
    missing = w.client.put(f"/api/v1/admin/tables/layout?restaurant_id={w.rid}", headers=w.ah,
                           json={"items": [{"id": w.t1.id, "pos_x": 1, "pos_y": 1}, {"id": 999999, "pos_x": 1, "pos_y": 1}]})
    assert missing.status_code == 404
    assert {t["id"]: t["pos_x"] for t in _list(w)}[w.t1.id] == 10   # all-or-nothing: nothing changed


def test_customer_floor_plan_states(world):
    w = world
    _update(w, w.t1.id, zone="Window", shape="ROUND", pos_x=10, pos_y=10)
    start = _now() + timedelta(hours=4)
    assert _admin_book(w, w.t2, start).status_code == 201                       # T2 taken at that time

    r = w.client.get(
        f"/api/v1/restaurants/{w.restaurant.slug}/reservations/availability",
        params={"starts_at": _iso(start), "party_size": 4},
    ).json()
    floor = {t["table_number"]: t for t in r["floor"]}
    assert set(floor) == {"T1", "T2", "T3"}
    assert floor["T1"]["state"] == "TOO_SMALL" and floor["T1"]["zone"] == "Window" and floor["T1"]["shape"] == "ROUND"
    assert floor["T2"]["state"] == "TOO_SMALL"                                  # seats 2 < party of 4
    assert floor["T3"]["state"] == "AVAILABLE"
    assert [t["table_number"] for t in r["tables"]] == ["T3"]

    r = w.client.get(
        f"/api/v1/restaurants/{w.restaurant.slug}/reservations/availability",
        params={"starts_at": _iso(start), "party_size": 2},
    ).json()
    assert {t["table_number"]: t["state"] for t in r["floor"]} == {"T1": "AVAILABLE", "T2": "UNAVAILABLE", "T3": "AVAILABLE"}


def test_customer_bookings_still_work_with_zones(world):
    w = world
    _update(w, w.t3.id, zone="Center")
    assert _book(w, w.t3, _now() + timedelta(hours=3), party=4).status_code == 201
    assert _table_status(w, w.t3)["zone"] == "Center"
