"""A small in-memory rate limiter (per client address, sliding time window).

Counters are per process. With API_WORKERS=2, effective limits
can double. Use one worker for strict limits.
"""
import threading
import time
from collections import defaultdict, deque

from fastapi import Request


class SlidingWindowLimiter:
    def __init__(self, limit: int, window_seconds: int):
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def _trim(self, key: str, now: float) -> deque:
        hits = self._hits[key]
        while hits and hits[0] <= now - self.window:
            hits.popleft()
        return hits

    def blocked(self, key: str) -> bool:
        """True when the key has already used up its allowance (does not count as a hit)."""
        with self._lock:
            return len(self._trim(key, time.monotonic())) >= self.limit

    def record(self, key: str) -> None:
        with self._lock:
            now = time.monotonic()
            self._trim(key, now).append(now)

    def allow(self, key: str) -> bool:
        """Count one request; False if it is over the limit."""
        with self._lock:
            now = time.monotonic()
            hits = self._trim(key, now)
            if len(hits) >= self.limit:
                return False
            hits.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


def client_key(request: Request) -> str:
    # The direct client address (the API is served by Uvicorn without a proxy).
    return request.client.host if request.client else "unknown"
