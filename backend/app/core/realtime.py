"""Real-time events (Server-Sent Events) fanned out through PostgreSQL LISTEN/NOTIFY.

Why Postgres and not an in-memory queue? The API runs several worker processes (and later,
several servers). An event published while handling a request on worker 1 must reach a kitchen
screen connected to worker 2. `pg_notify` gives that with no extra infrastructure, and it has a
property we want: a notification is delivered **only if the publishing transaction commits**, so
screens never hear about an order that was rolled back.

Flow:  service code -> publish(db, topic, ...)  ==pg_notify==>  every worker's PgListener thread
       -> broker.dispatch(topic, event) -> each subscribed SSE connection's queue -> browser.

Events are *hints* ("orders changed"), not state. Clients refetch what they need, so a missed event
(reconnect, full queue) is harmless. Payloads must stay tiny (Postgres limits them to ~8 KB).
"""

import asyncio
import json
import logging
import signal
import threading
import time
from dataclasses import dataclass, field
from typing import Any

import psycopg
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.config import settings

logger = logging.getLogger(__name__)

CHANNEL = "dineflow_events"
QUEUE_SIZE = 100
SHUTDOWN = {"type": "__shutdown__"}  # sentinel: tells every open stream to end


def kitchen_topic(restaurant_id: int) -> str:
    """Tenant-scoped topic: the kitchen screen of one restaurant."""
    return f"restaurant:{restaurant_id}:kitchen"


@dataclass(eq=False)
class Subscription:
    topic: str
    loop: asyncio.AbstractEventLoop
    queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=QUEUE_SIZE))


class Broker:
    """Tracks the SSE connections open in *this* process and hands them events."""

    def __init__(self) -> None:
        self._subs: dict[str, set[Subscription]] = {}
        self._lock = threading.Lock()

    def subscribe(self, topic: str) -> Subscription:
        """Call from the event-loop thread that will read the queue."""
        sub = Subscription(topic=topic, loop=asyncio.get_running_loop())
        with self._lock:
            self._subs.setdefault(topic, set()).add(sub)
        return sub

    def unsubscribe(self, sub: Subscription) -> None:
        with self._lock:
            bucket = self._subs.get(sub.topic)
            if bucket:
                bucket.discard(sub)
                if not bucket:
                    del self._subs[sub.topic]

    def count(self) -> int:
        with self._lock:
            return sum(len(b) for b in self._subs.values())

    def dispatch(self, topic: str, event: dict[str, Any]) -> int:
        """Thread-safe. Returns how many local connections were notified."""
        with self._lock:
            targets = list(self._subs.get(topic, ()))
        for sub in targets:
            try:
                sub.loop.call_soon_threadsafe(self._offer, sub, event)
            except RuntimeError:  # that connection's loop already closed
                self.unsubscribe(sub)
        return len(targets)

    def close_all(self) -> None:
        """Ask every open stream to finish. Thread- and signal-safe. Clients reconnect on their own."""
        with self._lock:
            targets = [sub for bucket in self._subs.values() for sub in bucket]
        for sub in targets:
            try:
                sub.loop.call_soon_threadsafe(self._offer, sub, SHUTDOWN, True)
            except RuntimeError:
                pass

    @staticmethod
    def _offer(sub: Subscription, event: dict[str, Any], force: bool = False) -> None:
        if force:
            while not sub.queue.empty():  # make room: shutdown must not be blocked by a backlog
                sub.queue.get_nowait()
        if sub.queue.full():
            # A stalled client: drop its backlog and tell it to refetch everything.
            while not sub.queue.empty():
                sub.queue.get_nowait()
            event = {"type": "resync"}
        sub.queue.put_nowait(event)


broker = Broker()


def publish(db: Session, topic: str, event_type: str, data: dict[str, Any] | None = None) -> None:
    """Announce an event. Runs inside the caller's transaction: delivered on COMMIT, dropped on rollback."""
    payload = json.dumps({"topic": topic, "event": {"type": event_type, **(data or {})}}, separators=(",", ":"))
    db.execute(text("SELECT pg_notify(:channel, :payload)"), {"channel": CHANNEL, "payload": payload})


def _listen_dsn() -> str:
    """SQLAlchemy URL (postgresql+psycopg://…) -> plain libpq URL for a dedicated LISTEN connection."""
    return make_url(settings.DATABASE_URL).set(drivername="postgresql").render_as_string(hide_password=False)


class PgListener(threading.Thread):
    """One dedicated connection per worker process that LISTENs and feeds the local broker."""

    def __init__(self, dsn: str | None = None) -> None:
        super().__init__(name="pg-realtime-listener", daemon=True)
        self._dsn = dsn or _listen_dsn()
        self._stop_event = threading.Event()
        self.connected = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        backoff = 1.0
        while not self._stop_event.is_set():
            try:
                with psycopg.connect(self._dsn, autocommit=True) as conn:
                    conn.execute(f"LISTEN {CHANNEL}")
                    logger.info("Realtime listener connected")
                    self.connected.set()
                    backoff = 1.0
                    while not self._stop_event.is_set():
                        for note in conn.notifies(timeout=1.0):
                            self._handle(note.payload)
            except Exception as exc:  # noqa: BLE001 — keep the API alive; retry with backoff
                self.connected.clear()
                logger.warning("Realtime listener lost its connection (%s); retrying in %.0fs", exc, backoff)
                self._stop_event.wait(backoff)
                backoff = min(backoff * 2, 30.0)
        self.connected.clear()

    @staticmethod
    def _handle(payload: str) -> None:
        try:
            message = json.loads(payload)
            broker.dispatch(message["topic"], message["event"])
        except (ValueError, KeyError, TypeError):
            logger.warning("Ignoring malformed realtime payload: %.200s", payload)


def install_shutdown_hook() -> None:
    """End live streams the moment the server is told to stop.

    Uvicorn waits for every open connection to close *before* it runs shutdown hooks, and an SSE
    stream never closes by itself — so without this a redeploy (or a dev auto-reload) hangs for as
    long as any kitchen screen is open. Runs on the main thread during startup, after uvicorn has
    installed its own handlers, and chains to them.
    """
    if threading.current_thread() is not threading.main_thread():
        return
    for signum in (signal.SIGTERM, signal.SIGINT):
        previous = signal.getsignal(signum)

        def handler(number, frame, _previous=previous):
            broker.close_all()
            if callable(_previous):
                _previous(number, frame)

        try:
            signal.signal(signum, handler)
        except (ValueError, OSError):  # not allowed in this context (e.g. some test runners)
            return


_listener: PgListener | None = None


def start_listener() -> None:
    global _listener
    if _listener is None or not _listener.is_alive():
        _listener = PgListener()
        _listener.start()


def stop_listener() -> None:
    global _listener
    if _listener is not None:
        _listener.stop()
        _listener.join(timeout=3)
        _listener = None


def wait_until(predicate, timeout: float = 5.0, interval: float = 0.02) -> bool:
    """Small helper for tests and startup checks."""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(interval)
    return False
