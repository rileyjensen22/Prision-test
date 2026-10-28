"""Sliding-window rate limiters. `SlidingWindowLimiter` keeps its counts in memory (one process).
`SharedWindowLimiter` keeps them in Postgres so several API processes, or machines sharing a
database, enforce one limit between them. Both have the same methods."""

import logging
import math
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
    """The same limiter with its counts in the `rate_limit_counts` table (Postgres).

    A sliding-window counter: one row per key and window holds how many hits fell in that window,
    and the allowance in use is the current window's count plus the previous window's count
    weighted by how much of it still overlaps the last `window` seconds. A check is one or two
    single-row statements however busy the key is, and the row lock on the counter is what stops
    two processes slipping under the limit together. Times come from the database clock, so every
    process agrees. If the database cannot be reached the limiter lets the request through (and
    logs it): a failed limiter must never block protected services such as Request staff.
    """

    # Where we are in the clock: the window number, how far into it, and both counts.
    _STATE = """
        WITH t AS (SELECT extract(epoch FROM clock_timestamp()) / :w AS x),
        w AS (SELECT floor(x)::bigint AS cur, x - floor(x) AS frac FROM t),
        c AS (SELECT coalesce(sum(n) FILTER (WHERE window_no = w.cur), 0) AS cur_n,
                     coalesce(sum(n) FILTER (WHERE window_no = w.cur - 1), 0) AS prev_n
              FROM w LEFT JOIN rate_limit_counts r
                ON r.bucket = :b AND r.key = :k AND r.window_no >= w.cur - 1)
    """

    # Counts a hit unless the allowance is used up. The conflict clause takes the row lock, so
    # two processes hitting the same key at once cannot both pass the check.
    _HIT = """
        INSERT INTO rate_limit_counts (bucket, key, window_no, n, start_s)
        SELECT :b, :k, w.cur, 1, w.cur * :w FROM w, c WHERE c.prev_n * (1 - w.frac) < :n
        ON CONFLICT (bucket, key, window_no) DO UPDATE SET n = rate_limit_counts.n + 1
        WHERE rate_limit_counts.n + (SELECT c.prev_n * (1 - w.frac) FROM w, c) < :n
        RETURNING n
    """

    def __init__(self, name: str, limit: int, window_seconds: float, clock=None):
        self.name, self.limit, self.window = name, limit, window_seconds
        # `clock` exists only so callers can treat both limiters alike; the database clock rules.

    def _run(self, fn, default):
        from isd import db

        try:
            with db.limiter_engine.connect() as conn:
                return fn(conn)
        except Exception:  # noqa: BLE001
            log.exception("shared rate limiter unavailable; allowing the request")
            return default

    def _p(self, key: str) -> dict:
        return {"b": self.name, "k": key[:128], "w": float(self.window), "n": self.limit}

    def _state(self, c, key: str) -> tuple[float, int, int]:
        """(fraction of the current window gone, count in it, count in the one before)."""
        row = c.execute(
            text(self._STATE + "SELECT w.frac, c.cur_n, c.prev_n FROM w, c"), self._p(key)
        ).one()
        return float(row[0]), int(row[1]), int(row[2])

    def count(self, key: str) -> int:
        def go(c):
            frac, cur, prev = self._state(c, key)
            return math.ceil(cur + prev * (1 - frac))

        return self._run(go, 0)

    def blocked(self, key: str) -> bool:
        return self.count(key) >= self.limit

    def retry_after(self, key: str) -> int:
        def go(c):
            frac, cur, prev = self._state(c, key)
            used = cur + prev * (1 - frac)
            if used < self.limit:
                return 0
            if cur >= self.limit or prev == 0:  # only the next window helps
                return max(1, math.ceil((1 - frac) * self.window))
            # the previous window's weight falls off linearly; find when the total drops under
            need = (used - self.limit + 1e-9) / prev  # share of `prev` that must fall away
            return max(1, math.ceil(need * self.window))

        return self._run(go, 0)

    def hit(self, key: str) -> bool:
        """Records one use. True if it was within the limit, False if over (an over-limit try is
        not counted, so a blocked client is free again when its old hits age out)."""

        def go(c):
            row = c.execute(text(self._STATE + self._HIT), self._p(key)).first()
            return row is not None

        return self._run(go, True)

    def reset(self, key: str) -> None:
        self._run(
            lambda c: c.execute(
                text("DELETE FROM rate_limit_counts WHERE bucket = :b AND key = :k"), self._p(key)
            ),
            None,
        )


def purge_old_hits(session, older_than_seconds: int = 86_400) -> int:
    """Housekeeping for the daily job: drops counters whose window ended long ago."""
    return session.execute(
        text(
            "DELETE FROM rate_limit_counts "
            "WHERE start_s < extract(epoch FROM clock_timestamp()) - :s"
        ),
        {"s": older_than_seconds},
    ).rowcount
