"""
Rate limiting (Phase 17).

WHY
    Without limits, one script (or one curious user) can flood the API: the
    LLM is slow and expensive, retraining uses the CPU for seconds, and an
    attacker could guess passwords quickly. A rate limit caps how many requests
    one client may make in a time window; beyond it the API answers
    429 Too Many Requests with a Retry-After header.

HOW: A SLIDING WINDOW
    For each (bucket, client) we keep the times of recent requests. A new
    request is allowed if fewer than `limit` happened in the last `window`
    seconds. "client" is the logged-in user, or the IP address otherwise.

    Buckets: "api" (every /api/v1 request), "chat" (the assistant), "admin"
    (retraining and uploads), "login" (password attempts).

LIMITS OF THIS VERSION
    Counts live in this process's memory: they reset on restart and are not
    shared between several API processes. Behind a load balancer (Phase 20),
    a shared store such as Redis would hold them instead; the interface stays.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from app.core.errors import AppError


class RateLimitedError(AppError):
    status_code = 429

    def __init__(self, retry_after: int, bucket: str) -> None:
        super().__init__("RATE_LIMITED", f"Too many {bucket} requests. Try again in {retry_after} s.")
        self.retry_after = retry_after


class RateLimiter:
    def __init__(self) -> None:
        self._hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, bucket: str, client: str, limit: int, window_seconds: float) -> None:
        """Record one request; raise RateLimitedError if the client is over the limit. limit 0 = no limit."""
        if limit <= 0:
            return
        now = time.monotonic()
        with self._lock:
            hits = self._hits[(bucket, client)]
            while hits and hits[0] <= now - window_seconds:
                hits.popleft()
            if len(hits) >= limit:
                raise RateLimitedError(max(1, int(hits[0] + window_seconds - now) + 1), bucket)
            hits.append(now)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


LIMITER = RateLimiter()  # one shared limiter per API process
