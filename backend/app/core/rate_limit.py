"""Small in-process sliding-window rate limiter.

Good enough to blunt password guessing and scripted abuse on a single instance. It is per
process, so with several workers the effective limit is multiplied; swap the storage for
Redis when we scale out (roadmap stage A2) — the interface stays the same.
"""

import threading
import time
from collections import deque

from fastapi import Depends, Request

from app.core.config import settings
from app.core.exceptions import TooManyRequestsError

_MAX_TRACKED_KEYS = 20_000


class RateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()

    def hit(self, key: str, limit: int, window_seconds: int) -> int | None:
        """Record a request. Returns None if allowed, else the seconds until it would be."""
        now = time.monotonic()
        with self._lock:
            if len(self._hits) > _MAX_TRACKED_KEYS:
                self._prune(now)
            bucket = self._hits.setdefault(key, deque())
            while bucket and now - bucket[0] >= window_seconds:
                bucket.popleft()
            if len(bucket) >= limit:
                return max(1, int(window_seconds - (now - bucket[0])) + 1)
            bucket.append(now)
            return None

    def enforce(self, key: str, limit: int, window_seconds: int) -> None:
        if not settings.RATE_LIMIT_ENABLED:
            return
        retry_after = self.hit(key, limit, window_seconds)
        if retry_after is not None:
            raise TooManyRequestsError(retry_after)

    def _prune(self, now: float) -> None:
        for key in [k for k, b in self._hits.items() if not b or now - b[-1] > 3600]:
            del self._hits[key]


limiter = RateLimiter()


def client_ip(request: Request) -> str:
    if settings.TRUST_PROXY_HEADERS:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limit(scope: str, limit: int, window_seconds: int):
    """Route dependency: at most `limit` requests per `window_seconds` per client IP."""

    def dependency(request: Request) -> None:
        limiter.enforce(f"{scope}:{client_ip(request)}", limit, window_seconds)

    return Depends(dependency)
