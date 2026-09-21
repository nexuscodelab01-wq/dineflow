"""Live status for customers and table guests: who may listen, and what gets announced."""

import asyncio
from types import SimpleNamespace

import pytest

from app.api.routes import orders as order_routes
from app.api.routes import table_ordering as table_routes
from app.core import realtime as rt
from app.models.enums import OrderStatus
from app.models.order import Order
from app.models.table_session import TableSession
from tests.tenants import header, make_tenant, place_order
from tests.test_table_ordering import join, send, world  # noqa: F401  (world is a fixture)

API = "/api/v1"


class FakeRequest:
    async def is_disconnected(self):
        return False


@pytest.fixture
def announced(monkeypatch):
    """Every event published during the test, as (topic, type, data)."""
    from app.services import admin_service, order_service, table_session_service

    calls = []
    spy = lambda db, topic, event_type, data=None: calls.append((topic, event_type, data or {}))  # noqa: E731
    for module in (rt, admin_service, order_service, table_session_service):   # each imports publish by name
        monkeypatch.setattr(module, "publish", spy)
    return calls


def set_status(w, tenant, order_id, status):
    return w.client.patch(f"{API}/admin/orders/{order_id}/status", params={"restaurant_id": tenant.rid},
                          headers=header(tenant.staff), json={"status": status})


# ------------------------------------------------------------------ what is announced

def test_a_status_change_reaches_the_customers_order_topic(world, announced):
    w = world
    order_id = place_order(w.client, w.a).json()["id"]
    announced.clear()
    assert set_status(w, w.a, order_id, "PREPARING").status_code == 200
    assert (f"order:{order_id}", "order.status", {"order_id": order_id, "status": "PREPARING"}) in announced
    assert not any(t.startswith("session:") for t, *_ in announced)       # a pickup order has no table


def test_a_table_orders_status_change_also_reaches_the_whole_table(world, announced):
    w = world
    guest = join(w, w.a, "Sam")
    order_id = send(w, w.a, guest).json()["order_id"]
    session_id = w.db.query(TableSession).filter_by(table_id=w.a.table.id).one().id
    assert (f"session:{session_id}", "round.created", {"order_id": order_id, "round_no": 1}) in announced

    announced.clear()
    set_status(w, w.a, order_id, "PREPARING")
    topics = {t for t, *_ in announced}
    assert {f"order:{order_id}", f"session:{session_id}", f"restaurant:{w.a.rid}:kitchen"} <= topics
    assert not any(f"restaurant:{w.b.rid}" in t for t in topics)         # nothing leaks to the other restaurant


def test_closing_a_tab_tells_the_guests_at_once(world, announced):
    w = world
    join(w, w.a)
    session = w.db.query(TableSession).filter_by(table_id=w.a.table.id).one()
    announced.clear()
    w.client.post(f"{API}/admin/table-sessions/{session.id}/close", params={"restaurant_id": w.a.rid}, headers=header(w.a.staff))
    assert (f"session:{session.id}", "session.closed", {"table_id": w.a.table.id}) in announced


# ------------------------------------------------------------------ who may listen

def test_only_the_owner_of_an_order_may_follow_it(world):
    w = world
    mine = place_order(w.client, w.a).json()["id"]
    assert w.client.get(f"{API}/orders/{mine}/stream").status_code == 401
    assert w.client.get(f"{API}/orders/{mine}/stream", headers=header(w.b.customer)).status_code == 404
    assert w.client.get(f"{API}/orders/{mine}/stream", headers=header(w.a.admin)).status_code == 404   # staff use the kitchen stream
    assert w.client.get(f"{API}/orders/999999/stream", headers=header(w.a.customer)).status_code == 404


def test_the_owner_gets_a_stream_on_exactly_their_orders_topic(world):
    w = world
    order_id = place_order(w.client, w.a).json()["id"]

    async def scenario():
        response = await order_routes.order_stream(
            order_id, FakeRequest(), w.a.customer, order_routes.get_order_service(w.db))
        assert response.media_type == "text/event-stream"
        first = await response.body_iterator.__anext__()
        assert "event: ready" in first and rt.broker.count() == 1
        rt.broker.dispatch(f"order:{order_id + 1}", {"type": "order.status"})   # someone else's order
        rt.broker.dispatch(f"order:{order_id}", {"type": "order.status", "status": "READY"})
        frame = await asyncio.wait_for(response.body_iterator.__anext__(), 1)
        assert "READY" in frame
        await response.body_iterator.aclose()
        assert rt.broker.count() == 0
    asyncio.run(scenario())


def test_table_streams_need_a_valid_table_pass(world):
    w = world
    guest = join(w, w.a)
    assert w.client.get(f"{API}/table-session/stream").status_code == 401
    assert w.client.get(f"{API}/table-session/stream", headers=header(w.a.customer)).status_code == 401
    assert w.client.get(f"{API}/table-session/stream", headers=header(w.a.admin)).status_code == 401
    session = w.db.query(TableSession).filter_by(table_id=w.a.table.id).one()
    w.client.post(f"{API}/admin/table-sessions/{session.id}/close", params={"restaurant_id": w.a.rid}, headers=header(w.a.staff))
    assert w.client.get(f"{API}/table-session/stream", headers=guest).status_code == 401     # tab ended


def test_a_guest_streams_only_their_own_tables_topic(world):
    w = world
    join(w, w.a)
    join(w, w.b)
    a_session = w.db.query(TableSession).filter_by(table_id=w.a.table.id).one()

    async def scenario():
        response = await table_routes.table_stream(FakeRequest(), SimpleNamespace(session=a_session))
        await response.body_iterator.__anext__()
        b_session = w.db.query(TableSession).filter_by(table_id=w.b.table.id).one()
        rt.broker.dispatch(f"session:{b_session.id}", {"type": "round.created"})
        rt.broker.dispatch(f"session:{a_session.id}", {"type": "session.closed"})
        frame = await asyncio.wait_for(response.body_iterator.__anext__(), 1)
        assert frame.startswith("event: session.closed")
        await response.body_iterator.aclose()
    asyncio.run(scenario())
