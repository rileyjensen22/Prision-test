"""The Postgres rate limiter: one limit shared by every process, fail-open if the store is down."""

import threading
import time
import uuid

import pytest
from sqlalchemy import create_engine

from isd import db, limits, settings
from isd.ratelimit import SharedWindowLimiter, SlidingWindowLimiter


@pytest.fixture(autouse=True)
def use_test_database(app_engine, monkeypatch):
    """The limiter reaches the database through isd.db.engine; point it at the test database."""
    monkeypatch.setattr(
        db, "limiter_engine", app_engine.execution_options(isolation_level="AUTOCOMMIT")
    )


def name() -> str:
    return f"t-{uuid.uuid4().hex[:8]}"


def test_two_limiters_share_one_count_like_two_processes():
    n = name()
    a, b = SharedWindowLimiter(n, 3, 60), SharedWindowLimiter(n, 3, 60)
    assert [a.hit("k"), b.hit("k"), a.hit("k")] == [True, True, True]
    assert b.hit("k") is False and a.hit("k") is False
    assert a.count("k") == 3 and b.blocked("k") and b.retry_after("k") > 0
    assert a.hit("other") is True  # another key has its own count


def test_the_window_slides_and_reset_clears_it():
    n = name()
    lim = SharedWindowLimiter(n, 2, 1)
    assert lim.hit("k") and lim.hit("k") and not lim.hit("k")
    time.sleep(1.2)
    assert lim.hit("k") is True
    lim.reset("k")
    assert lim.count("k") == 0


def test_concurrent_requests_cannot_slip_past_the_limit():
    lim = SharedWindowLimiter(name(), 5, 60)
    results = []

    def go():
        results.append(lim.hit("same"))

    threads = [threading.Thread(target=go) for _ in range(30)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert results.count(True) == 5


def test_an_unreachable_store_lets_requests_through(monkeypatch):
    monkeypatch.setattr(
        db, "limiter_engine", create_engine("postgresql+psycopg://x:y@127.0.0.1:1/none")
    )
    lim = SharedWindowLimiter(name(), 1, 60)
    assert lim.hit("k") is True and lim.hit("k") is True and lim.count("k") == 0


def test_security_limiters_are_shared_and_flood_guards_stay_local_unless_asked(monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_STORE", "postgres")
    monkeypatch.setattr(settings, "RATE_LIMIT_SHARE_ALL", False)
    try:
        limits.reset_defaults()
        for shared in ("login_failures", "login_attempts_ip", "pairing"):
            assert isinstance(limits.LIMITERS[shared], SharedWindowLimiter)
        for local in ("ip", "device", "staff"):
            assert isinstance(limits.LIMITERS[local], SlidingWindowLimiter)
        monkeypatch.setattr(settings, "RATE_LIMIT_SHARE_ALL", True)
        limits.reset_defaults()
        assert all(isinstance(lim, SharedWindowLimiter) for lim in limits.LIMITERS.values())
    finally:
        monkeypatch.undo()
        limits.reset_defaults()


def test_the_app_uses_the_shared_store_when_configured(client, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_STORE", "postgres")
    monkeypatch.setattr(settings, "RATE_LIMIT_SHARE_ALL", True)
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    try:
        lim = limits.configure("ip", 2, 60)
        assert isinstance(lim, SharedWindowLimiter)
        lim.reset("testclient")
        codes = [client.get("/health").status_code for _ in range(4)]
        assert codes[:2] == [200, 200] and codes[2:] == [429, 429]
    finally:
        limits.reset_defaults()
