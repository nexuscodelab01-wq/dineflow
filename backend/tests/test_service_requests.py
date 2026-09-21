"""Call the waiter / ask for the bill: idempotent asks, staff queue, live events, closing, isolation."""

import pytest

from app.models.service_request import ServiceRequest
from app.models.table_session import TableSession
from app.services.feature_service import FeatureService
from tests.tenants import header
from tests.test_live_status import announced  # noqa: F401  (fixture)
from tests.test_table_ordering import join, send, world  # noqa: F401  (world is a fixture)

API = "/api/v1"


def ask(w, guest, kind):
    return w.client.post(f"{API}/table-session/requests", headers=guest, json={"kind": kind})


def queue(w, tenant, who=None):
    return w.client.get(f"{API}/admin/service-requests", params={"restaurant_id": tenant.rid}, headers=header(who or tenant.staff))


def test_a_guest_can_call_the_waiter_and_staff_see_it(world):
    w = world
    sam = join(w, w.a, "Sam")
    r = ask(w, sam, "WAITER")
    assert r.status_code == 200 and r.json() == ["WAITER"]
    [item] = queue(w, w.a).json()
    assert (item["table_number"], item["kind"], item["asked_by"]) == ("A1", "WAITER", "Sam")
    assert w.client.get(f"{API}/table-session", headers=sam).json()["requests"] == ["WAITER"]       # the guest sees it too


def test_asking_again_is_still_one_request_and_announces_once(world, announced):
    w = world
    sam, kim = join(w, w.a, "Sam"), join(w, w.a, "Kim")
    announced.clear()
    for who in (sam, sam, kim):
        assert ask(w, who, "WAITER").status_code == 200
    assert len(queue(w, w.a).json()) == 1
    assert w.db.query(ServiceRequest).count() == 1
    assert [e for e in announced if e[1] == "request.created"].__len__() == 2      # kitchen topic + the table's topic, once


def test_the_bill_needs_something_on_the_tab(world):
    w = world
    sam = join(w, w.a, "Sam")
    early = ask(w, sam, "BILL")
    assert early.status_code == 400 and "nothing" in early.json()["detail"]
    send(w, w.a, sam)
    assert ask(w, sam, "BILL").json() == ["BILL"]
    assert ask(w, sam, "WAITER").json() == ["BILL", "WAITER"]


def test_only_known_kinds_are_accepted(world):
    w = world
    assert ask(w, join(w, w.a), "PIZZA").status_code == 422


def test_staff_answering_a_request_clears_it_and_tells_the_table(world, announced):
    w = world
    sam = join(w, w.a, "Sam")
    ask(w, sam, "WAITER")
    rid = queue(w, w.a).json()[0]["id"]
    announced.clear()
    params = {"restaurant_id": w.a.rid}
    assert w.client.post(f"{API}/admin/service-requests/{rid}/done", params=params, headers=header(w.a.staff)).status_code == 204
    assert queue(w, w.a).json() == []
    assert w.client.get(f"{API}/table-session", headers=sam).json()["requests"] == []
    session_id = w.db.query(TableSession).filter_by(table_id=w.a.table.id).one().id
    assert (f"session:{session_id}", "request.done", {"table_id": w.a.table.id, "kind": "WAITER"}) in announced
    assert w.client.post(f"{API}/admin/service-requests/{rid}/done", params=params, headers=header(w.a.staff)).status_code == 204   # twice is fine
    assert ask(w, sam, "WAITER").json() == ["WAITER"]                                                                            # and they can ask again


def test_open_tabs_show_what_each_table_is_waiting_for(world):
    w = world
    sam = join(w, w.a, "Sam")
    send(w, w.a, sam)
    ask(w, sam, "BILL")
    [tab] = w.client.get(f"{API}/admin/table-sessions", params={"restaurant_id": w.a.rid}, headers=header(w.a.staff)).json()
    assert tab["requests"] == ["BILL"]


def test_closing_a_tab_clears_its_requests(world):
    w = world
    sam = join(w, w.a, "Sam")
    ask(w, sam, "WAITER")
    sid = w.db.query(TableSession).filter_by(table_id=w.a.table.id).one().id
    w.client.post(f"{API}/admin/table-sessions/{sid}/close", params={"restaurant_id": w.a.rid}, headers=header(w.a.staff))
    assert queue(w, w.a).json() == []


def test_requests_stay_inside_their_restaurant_and_role(world):
    w = world
    ask(w, join(w, w.a, "Sam"), "WAITER")
    rid = queue(w, w.a).json()[0]["id"]
    assert queue(w, w.b).json() == []                                              # Bravo's staff see none of Alpha's
    assert queue(w, w.a, w.a.customer).status_code == 403
    assert w.client.get(f"{API}/admin/service-requests", params={"restaurant_id": w.a.rid}, headers=header(w.b.staff)).status_code == 403
    other = w.client.post(f"{API}/admin/service-requests/{rid}/done", params={"restaurant_id": w.b.rid}, headers=header(w.b.staff))
    assert other.status_code == 404                                                # can't answer another restaurant's request
    assert len(queue(w, w.a).json()) == 1
    assert w.client.post(f"{API}/table-session/requests", json={"kind": "WAITER"}).status_code == 401   # no pass, no ask
    assert w.client.post(f"{API}/table-session/requests", headers=header(w.a.customer), json={"kind": "WAITER"}).status_code == 401


def test_the_feature_flag_switches_requests_off(world):
    w = world
    sam = join(w, w.a)
    FeatureService(w.db).set(w.a.rid, "qr_table_ordering", False, w.boss)
    assert ask(w, sam, "WAITER").status_code == 403
    assert queue(w, w.a).status_code == 403
