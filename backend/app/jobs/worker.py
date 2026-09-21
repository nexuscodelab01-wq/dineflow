"""The job worker: claims due jobs and runs them, one at a time per worker."""

import logging
import os
import socket
import threading
import time

from app.core.config import settings
from app.core.realtime import job_wakeup
from app.db.session import SessionLocal
from app.jobs import handlers as handler_registry
from app.jobs.handlers import JobContext
from app.jobs.queue import claim_next, mark_failed, mark_succeeded, requeue_stuck

logger = logging.getLogger(__name__)

_REAP_EVERY_SECONDS = 60


def worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{threading.get_ident() % 10000}"


def run_one(worker: str | None = None) -> bool:
    """Run the next due job, if any. Returns True if one was processed (successfully or not)."""
    worker = worker or worker_id()
    with SessionLocal() as db:
        job = claim_next(db, worker)
        db.commit()  # release the row lock right away; the job now shows as running
        if job is None:
            return False

        handler = handler_registry.HANDLERS.get(job.type)
        if handler is None:
            mark_failed(db, _no_retry(job), f"No handler registered for job type '{job.type}'")
            db.commit()
            logger.error("Job %s has unknown type %r; marked dead", job.id, job.type)
            return True

        try:
            handler(job.payload, JobContext(job_id=job.id, attempt=job.attempts, restaurant_id=job.restaurant_id))
        except Exception as exc:  # noqa: BLE001 — any handler failure means "retry later"
            status = mark_failed(db, job, f"{type(exc).__name__}: {exc}")
            db.commit()
            logger.warning("Job %s (%s) failed on attempt %s/%s: %s -> %s", job.id, job.type, job.attempts, job.max_attempts, exc, status)
        else:
            mark_succeeded(db, job.id)
            db.commit()
            logger.info("Job %s (%s) done", job.id, job.type)
        return True


def _no_retry(job):
    job.attempts = job.max_attempts  # nothing will ever handle it; don't retry
    return job


def drain(worker: str | None = None, limit: int = 1000) -> int:
    """Run due jobs until none are left. Returns how many ran."""
    ran = 0
    while ran < limit and run_one(worker):
        ran += 1
    return ran


class JobWorker(threading.Thread):
    def __init__(self) -> None:
        super().__init__(name="job-worker", daemon=True)
        self._stop_event = threading.Event()
        self._last_reap = 0.0

    def stop(self) -> None:
        self._stop_event.set()
        job_wakeup.set()

    def run(self) -> None:
        worker = worker_id()
        logger.info("Job worker started (%s)", worker)
        while not self._stop_event.is_set():
            try:
                self._reap_if_due()
                drain(worker)
            except Exception:  # noqa: BLE001 — never let the loop die (e.g. database restart)
                logger.exception("Job worker loop error; retrying shortly")
                self._stop_event.wait(5)
                continue
            job_wakeup.wait(timeout=settings.JOB_POLL_SECONDS)  # instant on NOTIFY, safety-net poll otherwise
            job_wakeup.clear()
        logger.info("Job worker stopped")

    def _reap_if_due(self) -> None:
        if time.monotonic() - self._last_reap < _REAP_EVERY_SECONDS:
            return
        self._last_reap = time.monotonic()
        with SessionLocal() as db:
            recovered = requeue_stuck(db, settings.JOB_STUCK_MINUTES)
            db.commit()
        if recovered:
            logger.warning("Recovered %s job(s) left running by a stopped worker", recovered)


_worker: JobWorker | None = None


def start_worker() -> None:
    global _worker
    if _worker is None or not _worker.is_alive():
        _worker = JobWorker()
        _worker.start()


def stop_worker() -> None:
    global _worker
    if _worker is not None:
        _worker.stop()
        _worker.join(timeout=5)
        _worker = None
