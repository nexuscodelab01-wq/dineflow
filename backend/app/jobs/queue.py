"""A small, reliable job queue on PostgreSQL — no Redis to run.

* **Transactional**: `enqueue()` runs inside the caller's transaction. A job is created only if the
  order/booking that caused it commits, and can never be lost after it does (the "outbox" pattern).
* **Safe with many workers**: jobs are claimed with `FOR UPDATE SKIP LOCKED`, so each runs once at a
  time no matter how many workers or servers are polling.
* **Retries**: a failed job is retried with growing delays, then parked as `dead` for a human to look at.
* **Crash recovery**: a job stuck in `running` (its worker died) is put back in the queue.
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.realtime import JOBS_CHANNEL

logger = logging.getLogger(__name__)

# Seconds to wait before attempt 2, 3, 4… (the last value repeats).
BACKOFF_SECONDS = (30, 120, 600, 3600, 21600)


@dataclass
class ClaimedJob:
    id: int
    type: str
    payload: dict[str, Any]
    attempts: int
    max_attempts: int
    restaurant_id: int | None


def enqueue(
    db: Session,
    job_type: str,
    payload: dict[str, Any] | None = None,
    *,
    run_at: datetime | None = None,
    restaurant_id: int | None = None,
    dedupe_key: str | None = None,
    max_attempts: int = 5,
) -> int | None:
    """Queue a job inside the caller's transaction. Returns its id, or None if `dedupe_key` is already queued/running."""
    row = db.execute(
        text(
            """
            INSERT INTO jobs (type, payload, run_at, restaurant_id, dedupe_key, max_attempts)
            VALUES (:type, CAST(:payload AS jsonb), COALESCE(:run_at, now()), :restaurant_id, :dedupe_key, :max_attempts)
            ON CONFLICT (dedupe_key) WHERE dedupe_key IS NOT NULL AND status IN ('queued', 'running') DO NOTHING
            RETURNING id
            """
        ),
        {
            "type": job_type,
            "payload": json.dumps(payload or {}),
            "run_at": run_at,
            "restaurant_id": restaurant_id,
            "dedupe_key": dedupe_key,
            "max_attempts": max_attempts,
        },
    ).first()
    # Wakes idle workers — delivered only when this transaction commits, like the job itself.
    db.execute(text("SELECT pg_notify(:channel, '')"), {"channel": JOBS_CHANNEL})
    return row.id if row else None


def claim_next(db: Session, worker_id: str) -> ClaimedJob | None:
    """Atomically take the oldest due job. The caller must commit to release the row lock."""
    row = db.execute(
        text(
            """
            UPDATE jobs SET status = 'running', locked_at = now(), locked_by = :worker, attempts = attempts + 1
            WHERE id = (
                SELECT id FROM jobs
                WHERE status = 'queued' AND run_at <= now()
                ORDER BY run_at, id
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            )
            RETURNING id, type, payload, attempts, max_attempts, restaurant_id
            """
        ),
        {"worker": worker_id},
    ).first()
    return ClaimedJob(row.id, row.type, row.payload, row.attempts, row.max_attempts, row.restaurant_id) if row else None


def mark_succeeded(db: Session, job_id: int) -> None:
    db.execute(
        text("UPDATE jobs SET status = 'succeeded', finished_at = now(), locked_at = NULL, locked_by = NULL, last_error = NULL WHERE id = :id"),
        {"id": job_id},
    )


def mark_failed(db: Session, job: ClaimedJob, error: str) -> str:
    """Retry later, or give up. Returns the new status ('queued' or 'dead')."""
    error = error[:2000]
    if job.attempts >= job.max_attempts:
        db.execute(
            text("UPDATE jobs SET status = 'dead', finished_at = now(), locked_at = NULL, locked_by = NULL, last_error = :e WHERE id = :id"),
            {"id": job.id, "e": error},
        )
        return "dead"
    delay = BACKOFF_SECONDS[min(job.attempts - 1, len(BACKOFF_SECONDS) - 1)]
    db.execute(
        text(
            "UPDATE jobs SET status = 'queued', run_at = now() + make_interval(secs => :delay), "
            "locked_at = NULL, locked_by = NULL, last_error = :e WHERE id = :id"
        ),
        {"id": job.id, "e": error, "delay": delay},
    )
    return "queued"


def requeue_stuck(db: Session, stuck_minutes: int) -> int:
    """Recover jobs whose worker died mid-run. Out-of-attempts jobs become `dead` instead of looping forever."""
    result = db.execute(
        text(
            """
            UPDATE jobs SET
                status = CASE WHEN attempts >= max_attempts THEN 'dead' ELSE 'queued' END,
                finished_at = CASE WHEN attempts >= max_attempts THEN now() ELSE NULL END,
                locked_at = NULL, locked_by = NULL,
                last_error = 'Worker stopped before finishing this job'
            WHERE status = 'running' AND locked_at < now() - make_interval(mins => :minutes)
            """
        ),
        {"minutes": stuck_minutes},
    )
    return result.rowcount or 0
