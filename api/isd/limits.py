"""The app's named rate limiters and the FastAPI dependencies that use them."""

import logging
import os
import time
from collections.abc import Callable

from fastapi import HTTPException, Request

from isd import settings
from isd.ratelimit import SharedWindowLimiter, SlidingWindowLimiter


def _env(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


log = logging.getLogger("isd.limits")
LIMITERS: dict[str, SlidingWindowLimiter | SharedWindowLimiter] = {}


# With RATE_LIMIT_STORE=postgres these limiters are shared by every API process, because their
# limits are exact security controls (lockout after failed sign-ins, pairing attempts). The
# per-request flood guards below them (`ip`, `device`, `staff`) run on every request, and a database
# round trip each made a full-size facility's kiosks several times slower in the load test, so they
# count per process unless RATE_LIMIT_SHARE_ALL=true: with N processes a client can use up to N
# times its allowance, which is acceptable for a coarse flood guard.
SHARED = frozenset({"login_failures", "login_attempts_ip", "pairing"})


def _shared(name: str) -> bool:
    return settings.RATE_LIMIT_STORE == "postgres" and (
        name in SHARED or settings.RATE_LIMIT_SHARE_ALL
    )


def configure(
    name: str, limit: int, window: float, clock: Callable[[], float] | None = None
) -> SlidingWindowLimiter | SharedWindowLimiter:
    if clock is None and _shared(name):
        lim: SlidingWindowLimiter | SharedWindowLimiter = SharedWindowLimiter(name, limit, window)
    else:  # in memory (development), or a test that supplies its own clock
        lim = (
            SlidingWindowLimiter(limit, window, clock)
            if clock
            else SlidingWindowLimiter(limit, window)
        )
    LIMITERS[name] = lim
    return lim


def reset_defaults() -> None:
    configure("login_failures", _env("LOGIN_MAX_FAILURES", 5), _env("LOGIN_LOCK_SECONDS", 900))
    configure("login_attempts_ip", _env("LOGIN_MAX_PER_MINUTE_IP", 60), 60)
    configure("device", _env("DEVICE_MAX_PER_MINUTE", 300), 60)
    configure("staff", _env("STAFF_MAX_PER_MINUTE", 600), 60)
    configure("ip", _env("IP_MAX_PER_MINUTE", 1200), 60)
    configure("pairing", _env("PAIRING_MAX_PER_MINUTE_IP", 10), 60)


reset_defaults()


def client_ip(request: Request) -> str:
    # Behind a reverse proxy, run uvicorn with --proxy-headers and --forwarded-allow-ips set to
    # the proxy; request.client then holds the real address. We never trust X-Forwarded-For here.
    return request.client.host if request.client else "unknown"


def _too_many(lim: SlidingWindowLimiter | SharedWindowLimiter, key: str) -> HTTPException:
    return HTTPException(
        429, "too many requests", headers={"Retry-After": str(lim.retry_after(key))}
    )


def ip_limit(request: Request) -> None:
    """Applied to every route (FastAPI app dependency), public ones included."""
    enforce("ip", client_ip(request))


SLOW_CHECK_SECONDS = 0.25


def enforce(name: str, key: str) -> None:
    if not settings.RATE_LIMIT_ENABLED:
        return
    lim = LIMITERS[name]
    started = time.perf_counter()
    allowed = lim.hit(key)
    took = time.perf_counter() - started
    if took > SLOW_CHECK_SECONDS:  # a slow limiter slows every request: make it visible
        log.warning("slow rate-limit check: %s took %.0f ms", name, took * 1000)
    if not allowed:
        raise _too_many(lim, key)
