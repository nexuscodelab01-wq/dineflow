"""Real-time events: broker fan-out, Postgres NOTIFY delivery, the SSE stream and its endpoint."""

import asyncio
import json
from types import SimpleNamespace

import pytest

from app.api.routes import realtime as realtime_routes
from app.core import realtime as rt
from app.core.config import settings
from app.db.session import SessionLocal
from tests.test_admin_management import place_order, url, world  # noqa: F401  (world is a fixture)


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------- broker

def test_events_only_reach_subscribers_of_that_topic():
    async def scenario():
        a, b = rt.broker.subscribe("restaurant:1:kitchen"), rt.broker.subscribe("restaurant:2:kitchen")
        try:
            assert rt.broker.dispatch("restaurant:1:kitchen", {"type": "order.created", "order_id": 7}) == 1
            assert (await asyncio.wait_for(a.queue.get(), 1))["order_id"] == 7
            await asyncio.sleep(0.05)
            assert b.queue.empty()                       # another restaurant never hears it
            assert rt.broker.dispatch("restaurant:9:kitchen", {"type": "x"}) == 0
        finally:
            rt.broker.unsubscribe(a); rt.broker.unsubscribe(b)
        assert rt.broker.count() == 0
    run(scenario())


def test_a_stalled_client_gets_a_resync_instead_of_a_growing_backlog():
    async def scenario():
        sub = rt.broker.subscribe("t")
        try:
            for i in range(rt.QUEUE_SIZE + 5):
                rt.broker.dispatch("t", {"type": "order.status", "n": i})
            await asyncio.sleep(0.1)
            drained = []
            while not sub.queue.empty():
                drained.append(sub.queue.get_nowait())
            assert drained[0] == {"type": "resync"}          # backlog dropped; client told to refetch
            assert len(drained) <= rt.QUEUE_SIZE and drained[-1]["n"] == rt.QUEUE_SIZE + 4   # newer events still arrive
        finally:
            rt.broker.unsubscribe(sub)
    run(scenario())


# ---------------------------------------------------------------- Postgres NOTIFY -> broker

def test_notifications_are_delivered_on_commit_and_dropped_on_rollback():
    async def scenario():
        listener = rt.PgListener()
        listener.start()
        assert await asyncio.to_thread(listener.connected.wait, 5), "listener never connected"
        sub = rt.broker.subscribe("restaurant:42:kitchen")
        try:
            with SessionLocal() as session:                       # rolled back -> nobody hears it
                rt.publish(session, "restaurant:42:kitchen", "order.created", {"order_id": 1})
                session.rollback()
            await asyncio.sleep(0.5)
            assert sub.queue.empty()

            with SessionLocal() as session:                       # committed -> delivered
                rt.publish(session, "restaurant:42:kitchen", "order.created", {"order_id": 2})
                session.commit()
            event = await asyncio.wait_for(sub.queue.get(), 5)
            assert event == {"type": "order.created", "order_id": 2}

            with SessionLocal() as session:                       # other tenants' topics stay separate
                rt.publish(session, "restaurant:43:kitchen", "order.created", {"order_id": 3})
                session.commit()
            await asyncio.sleep(0.5)
            assert sub.queue.empty()
        finally:
            rt.broker.unsubscribe(sub)
            listener.stop()
    run(scenario())


def test_malformed_notifications_are_ignored():
    rt.PgListener._handle("not json")
    rt.PgListener._handle('{"topic": "x"}')          # missing event
    rt.PgListener._handle("[1, 2]")


# ---------------------------------------------------------------- SSE stream

class FakeRequest:
    def __init__(self):
        self.disconnected = False

    async def is_disconnected(self):
        return self.disconnected


def test_stream_says_ready_forwards_events_pings_and_cleans_up(monkeypatch):
    monkeypatch.setattr(realtime_routes, "HEARTBEAT_SECONDS", 0.1)

    async def scenario():
        request = FakeRequest()
        stream = realtime_routes._event_stream(request, "restaurant:5:kitchen")
        first = await stream.__anext__()
        assert rt.broker.count() == 1
        assert "retry: 3000" in first and "event: ready" in first

        rt.broker.dispatch("restaurant:5:kitchen", {"type": "order.status", "order_id": 9, "status": "READY"})
        frame = await asyncio.wait_for(stream.__anext__(), 1)
        assert frame.startswith("event: order.status\ndata: ")
        assert json.loads(frame.split("data: ")[1]) == {"type": "order.status", "order_id": 9, "status": "READY"}
        assert frame.endswith("\n\n")

        assert await asyncio.wait_for(stream.__anext__(), 1) == ": ping\n\n"     # idle -> heartbeat

        request.disconnected = True                                              # client went away
        with pytest.raises(StopAsyncIteration):
            await asyncio.wait_for(stream.__anext__(), 1)
        assert rt.broker.count() == 0                                            # no leaked subscription
    run(scenario())


def test_stream_unsubscribes_when_cancelled():
    async def scenario():
        stream = realtime_routes._event_stream(FakeRequest(), "t")
        await stream.__anext__()
        assert rt.broker.count() == 1
        await stream.aclose()
        assert rt.broker.count() == 0


def test_a_stream_that_never_starts_registers_nothing():
    """Regression: subscribing in the endpoint leaked when the client vanished before streaming began."""
    async def scenario():
        response = await realtime_routes.kitchen_stream(FakeRequest(), SimpleNamespace(), restaurant_id=3)
        await response.body_iterator.aclose()            # never iterated
        assert rt.broker.count() == 0
    run(scenario())
    run(scenario())


def test_endpoint_returns_an_event_stream_for_the_right_topic():
    async def scenario():
        response = await realtime_routes.kitchen_stream(FakeRequest(), SimpleNamespace(), restaurant_id=11)
        assert response.media_type == "text/event-stream"
        assert response.headers["x-accel-buffering"] == "no" and "no-cache" in response.headers["cache-control"]
        try:
            assert "event: ready" in await response.body_iterator.__anext__()      # stream started -> subscribed
            assert rt.broker.dispatch(rt.kitchen_topic(11), {"type": "order.created"}) == 1
            assert rt.broker.dispatch(rt.kitchen_topic(12), {"type": "order.created"}) == 0
        finally:
            await response.body_iterator.aclose()
        assert rt.broker.count() == 0
    run(scenario())


# ---------------------------------------------------------------- endpoint access control

def test_only_staff_of_the_restaurant_can_open_the_stream(world, monkeypatch):
    w = world
    monkeypatch.setattr(settings, "REALTIME_MAX_STREAMS", 0)          # so allowed requests return at once (503) instead of streaming
    path = "/api/v1/admin/kitchen/stream"
    assert w.client.get(f"{path}?restaurant_id={w.a.id}").status_code == 401
    assert w.client.get(f"{path}?restaurant_id={w.a.id}", headers=w.customer).status_code == 403
    assert w.client.get(f"{path}?restaurant_id={w.a.id}", headers=w.admin_b).status_code == 403     # another restaurant's admin
    for headers in (w.staff, w.admin):                                                              # passes auth, then hits the cap
        assert w.client.get(f"{path}?restaurant_id={w.a.id}", headers=headers).status_code == 503


# ---------------------------------------------------------------- services publish

def test_orders_and_status_changes_publish_to_that_restaurants_kitchen(world, monkeypatch):
    w = world
    calls = []
    for module in ("app.services.order_service", "app.services.admin_service"):
        monkeypatch.setattr(f"{module}.publish", lambda db, topic, kind, data=None, _c=calls: _c.append((topic, kind, data)))

    oid = place_order(w).json()["id"]
    assert calls[-1][:2] == (rt.kitchen_topic(w.a.id), "order.created") and calls[-1][2]["order_id"] == oid

    w.client.patch(url(w, f"/orders/{oid}/status"), headers=w.staff, json={"status": "PREPARING"})
    assert calls[-1] == (rt.kitchen_topic(w.a.id), "order.status", {"order_id": oid, "status": "PREPARING"})

    before = len(calls)
    w.client.patch(url(w, f"/orders/{oid}/status"), headers=w.staff, json={"status": "PENDING"})   # invalid move -> rejected
    assert len(calls) == before                                                                     # nothing announced
