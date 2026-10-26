"""Sliding-window rate limiters. `SlidingWindowLimiter` keeps its counts in memory (one process).
`SharedWindowLimiter` keeps them in Postgres so several API processes, or machines sharing a
database, enforce one limit between them. Both have the same methods."""

import logging
import time
from collections import deque
from collections.abc import Callable

from sqlalchemy import text

log = logging.getLogger("isd.ratelimit")


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


class SharedWindowLimiter:
    """The same limiter with its hits stored in the `rate_limit_hits` table (Postgres).

    Each hit takes a short per-key advisory lock, so two processes cannot both slip under the
    limit. Times come from the database clock, so every process agrees. If the database cannot be
    reached the limiter lets the request through (and logs it): a failed limiter must never block
    protected services such as Request staff.
    """

    def __init__(self, name: str, limit: int, window_seconds: float, clock=None):
        self.name, self.limit, self.window = name, limit, window_seconds
        # `clock` exists only so callers can treat both limiters alike; the database clock rules.

    def _run(self, fn, default):
        from isd.db import engine

        try:
            with engine.begin() as conn:
                return fn(conn)
        except Exception:  # noqa: BLE001
            log.exception("shared rate limiter unavailable; allowing the request")
            return default

    def _p(self, key: str) -> dict:
        return {"b": self.name, "k": key[:128], "w": self.window, "n": self.limit}

    def count(self, key: str) -> int:
        return self._run(
            lambda c: c.execute(
                text(
                    "SELECT count(*) FROM rate_limit_hits WHERE bucket = :b AND key = :k "
                    "AND hit_at > clock_timestamp() - :w * interval '1 second'"
                ),
                self._p(key),
            ).scalar(),
            0,
        )

    def blocked(self, key: str) -> bool:
        return self.count(key) >= self.limit

    def retry_after(self, key: str) -> int:
        def go(c):
            oldest = c.execute(
                text(
                    "SELECT extract(epoch FROM (min(hit_at) + :w * interval '1 second' "
                    "- clock_timestamp())) FROM rate_limit_hits WHERE bucket = :b AND key = :k "
                    "AND hit_at > clock_timestamp() - :w * interval '1 second'"
                ),
                self._p(key),
            ).scalar()
            return 0 if oldest is None else max(1, int(oldest) + 1)

        return self._run(go, 0)

    def hit(self, key: str) -> bool:
        """Records one use. True if it was within the limit, False if over."""

        def go(c):
            p = self._p(key)
            c.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:b || '|' || :k, 0))"), p)
            row = c.execute(
                text(
                    "WITH gone AS (DELETE FROM rate_limit_hits WHERE bucket = :b AND key = :k "
                    "AND hit_at <= clock_timestamp() - :w * interval '1 second') "
                    "INSERT INTO rate_limit_hits (bucket, key) "
                    "SELECT :b, :k WHERE (SELECT count(*) FROM rate_limit_hits WHERE bucket = :b "
                    "AND key = :k AND hit_at > clock_timestamp() - :w * interval '1 second') < :n "
                    "RETURNING id"
                ),
                p,
            ).first()
            return row is not None

        return self._run(go, True)

    def reset(self, key: str) -> None:
        self._run(
            lambda c: c.execute(
                text("DELETE FROM rate_limit_hits WHERE bucket = :b AND key = :k"), self._p(key)
            ),
            None,
        )


def purge_old_hits(session, older_than_seconds: int = 86_400) -> int:
    """Housekeeping for the daily job: drops hits no window can still count."""
    return session.execute(
        text(
            "DELETE FROM rate_limit_hits "
            "WHERE hit_at < clock_timestamp() - :s * interval '1 second'"
        ),
        {"s": older_than_seconds},
    ).rowcount
