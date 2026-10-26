"""The app's named rate limiters and the FastAPI dependencies that use them."""

import os
from collections.abc import Callable

from fastapi import HTTPException, Request

from isd import settings
from isd.ratelimit import SharedWindowLimiter, SlidingWindowLimiter


def _env(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


LIMITERS: dict[str, SlidingWindowLimiter | SharedWindowLimiter] = {}


def configure(
    name: str, limit: int, window: float, clock: Callable[[], float] | None = None
) -> SlidingWindowLimiter | SharedWindowLimiter:
    if clock is None and settings.RATE_LIMIT_STORE == "postgres":
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


def enforce(name: str, key: str) -> None:
    if not settings.RATE_LIMIT_ENABLED:
        return
    lim = LIMITERS[name]
    if not lim.hit(key):
        raise _too_many(lim, key)
