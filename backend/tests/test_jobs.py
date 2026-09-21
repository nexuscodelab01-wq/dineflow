"""Background job queue: transactional enqueue, safe concurrent claiming, retries, recovery, wake-ups."""

import threading
import time
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.core import realtime as rt
from app.core.config import settings
from app.db.session import SessionLocal
from app.jobs import handlers, queue, worker


@pytest.fixture(autouse=True)
def clean_test_jobs():
    """Some tests commit for real (multi-connection behaviour); remove their rows afterwards."""
    yield
    with SessionLocal() as db:
        db.execute(text("DELETE FROM jobs WHERE type LIKE 'test\\_%'"))
        db.commit()


def status_of(db, job_id):
    return db.execute(text("SELECT status, attempts, last_error, run_at, locked_by FROM jobs WHERE id = :i"), {"i": job_id}).one()


# ---------------------------------------------------------------- enqueue is transactional

def test_a_job_exists_only_if_its_transaction_commits():
    with SessionLocal() as db:
        rolled_back = queue.enqueue(db, "test_x", {"n": 1})
        db.rollback()
    with SessionLocal() as db:
        committed = queue.enqueue(db, "test_x", {"n": 2})
        db.commit()
    with SessionLocal() as db:
        ids = {r.id for r in db.execute(text("SELECT id FROM jobs WHERE type = 'test_x'"))}
    assert committed in ids and rolled_back not in ids


def test_dedupe_key_prevents_duplicates_only_while_active(db):
    first = queue.enqueue(db, "test_d", dedupe_key="test:once")
    assert first is not None
    assert queue.enqueue(db, "test_d", dedupe_key="test:once") is None            # already queued
    job = queue.claim_next(db, "w")
    assert job.id == first and queue.enqueue(db, "test_d", dedupe_key="test:once") is None   # running counts too
    queue.mark_succeeded(db, first)
    assert queue.enqueue(db, "test_d", dedupe_key="test:once") is not None        # finished: may queue again


# ---------------------------------------------------------------- claiming

def test_jobs_are_claimed_oldest_first_and_only_when_due(db):
    later = queue.enqueue(db, "test_c", run_at=datetime.now(timezone.utc) + timedelta(hours=1))
    a = queue.enqueue(db, "test_c", {"i": "a"})
    b = queue.enqueue(db, "test_c", {"i": "b"})
    first = queue.claim_next(db, "worker-1")
    assert first.id == a and first.attempts == 1 and first.payload == {"i": "a"}
    assert status_of(db, a).status == "running" and status_of(db, a).locked_by == "worker-1"
    assert queue.claim_next(db, "worker-2").id == b                                  # a is taken, next one
    assert queue.claim_next(db, "worker-3") is None                                  # the future job isn't due
    assert status_of(db, later).status == "queued"


def test_many_workers_never_run_the_same_job_twice():
    """SKIP LOCKED: 4 competing workers over 40 jobs — every job runs exactly once."""
    with SessionLocal() as db:
        ids = [queue.enqueue(db, "test_race", {"n": i}) for i in range(40)]
        db.commit()
    ran: list[int] = []
    lock = threading.Lock()

    def handle(payload, ctx):
        time.sleep(0.005)
        with lock:
            ran.append(ctx.job_id)

    handlers.HANDLERS["test_race"] = handle
    try:
        threads = [threading.Thread(target=lambda n=n: [None for _ in iter(lambda: worker.run_one(f"w{n}"), False)]) for n in range(4)]
        [t.start() for t in threads]
        [t.join(30) for t in threads]
    finally:
        handlers.HANDLERS.pop("test_race", None)
    assert sorted(ran) == sorted(ids)
    with SessionLocal() as db:
        assert {r.status for r in db.execute(text("SELECT status FROM jobs WHERE type = 'test_race'"))} == {"succeeded"}


# ---------------------------------------------------------------- outcomes

def run_with_handler(name, fn):
    handlers.HANDLERS[name] = fn
    try:
        return worker.run_one("test-worker")
    finally:
        handlers.HANDLERS.pop(name, None)


def test_success_failure_retry_and_death():
    with SessionLocal() as db:
        ok = queue.enqueue(db, "test_ok", max_attempts=2)
        db.commit()
    assert run_with_handler("test_ok", lambda p, c: None) is True
    with SessionLocal() as db:
        assert status_of(db, ok).status == "succeeded"

    with SessionLocal() as db:
        bad = queue.enqueue(db, "test_bad", max_attempts=2)
        db.commit()

    def boom(p, c):
        raise RuntimeError("mail server on fire")

    assert run_with_handler("test_bad", boom) is True                                # attempt 1 -> retry later
    with SessionLocal() as db:
        row = status_of(db, bad)
        assert (row.status, row.attempts) == ("queued", 1) and "mail server on fire" in row.last_error
        delay = (row.run_at - datetime.now(timezone.utc)).total_seconds()
        assert 20 < delay <= 31                                                      # first backoff: 30 s
        db.execute(text("UPDATE jobs SET run_at = now() WHERE id = :i"), {"i": bad}); db.commit()
    assert run_with_handler("test_bad", boom) is True                                # attempt 2 of 2 -> dead
    with SessionLocal() as db:
        assert status_of(db, bad).status == "dead" and status_of(db, bad).attempts == 2


def test_backoff_grows_and_caps():
    class J:  # minimal stand-in for a claimed job
        def __init__(self, attempts): self.id, self.attempts, self.max_attempts = 0, attempts, 99
    assert [queue.BACKOFF_SECONDS[min(a - 1, len(queue.BACKOFF_SECONDS) - 1)] for a in (1, 2, 3, 4, 5, 6, 50)] == [30, 120, 600, 3600, 21600, 21600, 21600]


def test_unknown_job_types_are_parked_not_retried_forever():
    with SessionLocal() as db:
        jid = queue.enqueue(db, "test_no_such_handler")
        db.commit()
    assert worker.run_one("w") is True
    with SessionLocal() as db:
        row = status_of(db, jid)
        assert row.status == "dead" and "No handler" in row.last_error


# ---------------------------------------------------------------- crash recovery

def test_jobs_left_running_by_a_crashed_worker_are_recovered(db):
    stuck = queue.enqueue(db, "test_s")
    exhausted = queue.enqueue(db, "test_s", max_attempts=1)
    fresh = queue.enqueue(db, "test_s")
    for _ in range(3):
        queue.claim_next(db, "crashed-worker")
    db.execute(text("UPDATE jobs SET locked_at = now() - interval '30 minutes' WHERE id IN (:a, :b)"), {"a": stuck, "b": exhausted})
    assert queue.requeue_stuck(db, stuck_minutes=10) == 2
    assert status_of(db, stuck).status == "queued"                                   # will be retried
    assert status_of(db, exhausted).status == "dead"                                 # already used its only attempt
    assert status_of(db, fresh).status == "running"                                  # recently started: left alone


# ---------------------------------------------------------------- the worker thread

def test_notify_wakes_an_idle_worker_immediately(monkeypatch):
    monkeypatch.setattr(settings, "JOB_POLL_SECONDS", 30)                            # so only NOTIFY can explain a fast run
    done = threading.Event()
    handlers.HANDLERS["test_wake"] = lambda p, c: done.set()
    listener = rt.PgListener(); listener.start()
    assert listener.connected.wait(5)
    w = worker.JobWorker(); w.start()
    try:
        time.sleep(0.5)                                                              # worker is now idle, waiting
        started = time.monotonic()
        with SessionLocal() as db:
            queue.enqueue(db, "test_wake")
            db.commit()
        assert done.wait(5), "the job was not picked up"
        assert time.monotonic() - started < 3
    finally:
        handlers.HANDLERS.pop("test_wake", None)
        w.stop(); w.join(5); listener.stop()
