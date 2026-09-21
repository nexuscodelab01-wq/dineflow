"""Dedicated job worker process:  python -m app.worker  [--once]

Use this for heavier or production deployments (run the API with RUN_JOB_WORKER=false). `--once` drains
the queue and exits, handy for a cron job or a one-off catch-up.
"""

import argparse
import logging
import signal
import threading

from app.core.config import settings
from app.core.logging import setup_logging
from app.core.realtime import start_listener, stop_listener
from app.jobs.worker import JobWorker, drain

logger = logging.getLogger("app.worker")


def main() -> None:
    parser = argparse.ArgumentParser(description="DineFlow background job worker")
    parser.add_argument("--once", action="store_true", help="run all due jobs, then exit")
    args = parser.parse_args()

    setup_logging()
    settings.assert_production_ready()

    if args.once:
        logger.info("Ran %s job(s)", drain())
        return

    stop = threading.Event()
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda *_: stop.set())

    start_listener()  # so new jobs wake this worker immediately
    worker = JobWorker()
    worker.start()
    logger.info("Worker running. Ctrl+C to stop.")
    stop.wait()
    worker.stop()
    worker.join(timeout=10)
    stop_listener()


if __name__ == "__main__":
    main()
