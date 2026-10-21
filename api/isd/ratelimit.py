"""Small in-memory sliding-window rate limiter (single process). Replace with a shared store
(for example Redis) if the API runs on several machines."""

import time
from collections import deque
from collections.abc import Callable


class SlidingWindowLimiter:
    def __init__(
        self, limit: int, window_seconds: float, clock: Callable[[], float] = time.monotonic
    ):
        self.limit, self.window, self._clock = limit, window_seconds, clock
        self._hits: dict[str, deque[float]] = {}

    def _trim(self, key: str) -> deque[float]:
        q = self._hits.setdefault(key, deque())
        cutoff = self._clock() - self.window
        while q and q[0] <= cutoff:
            q.popleft()
        if not q:
            self._hits.pop(key, None)
            return deque()
        return q

    def count(self, key: str) -> int:
        return len(self._trim(key))

    def blocked(self, key: str) -> bool:
        return self.count(key) >= self.limit

    def retry_after(self, key: str) -> int:
        q = self._trim(key)
        if len(q) < self.limit:
            return 0
        return max(1, int(q[0] + self.window - self._clock()) + 1)

    def hit(self, key: str) -> bool:
        """Records one use. Returns True if it was within the limit (False = over the limit)."""
        q = self._trim(key) or self._hits.setdefault(key, deque())
        if len(q) >= self.limit:
            return False
        q.append(self._clock())
        self._hits[key] = q
        return True

    def reset(self, key: str) -> None:
        self._hits.pop(key, None)
