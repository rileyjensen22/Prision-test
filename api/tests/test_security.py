import re

import pytest
from sqlalchemy.orm import Session

from isd import settings
from isd.auth import hash_password, make_token, parse_token
from isd.main import app
from isd.models import ROLES, Staff
from isd.ratelimit import SlidingWindowLimiter
from tests.helpers import documented_operations, iter_api_routes, operations

pytestmark = pytest.mark.usefixtures("committed_config")
PUBLIC = {
    "/health",
    "/auth/login",
    "/auth/sso",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/docs/oauth2-redirect",
}


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def advance(self, s):
        self.t += s


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def person(owner_engine):
    """A committed staff account with a known password."""
    import uuid

    name = f"sec_{uuid.uuid4().hex[:8]}"
    with Session(owner_engine) as s, s.begin():
        st = Staff(
            username=name, role="officer", password_hash=hash_password("correct horse battery")
        )
        s.add(st)
        s.flush()
        return st.id, name


# ---------------- rate limiter ----------------
def test_sliding_window_limits_and_recovers(clock):
    lim = SlidingWindowLimiter(3, 60, clock)
    assert [lim.hit("a") for _ in range(4)] == [True, True, True, False]
    assert lim.blocked("a") and lim.retry_after("a") == 61 - 0 or lim.retry_after("a") > 0
    assert lim.hit("other")  # keys are independent
    clock.advance(30)
    assert not lim.hit("a")
    clock.advance(31)  # the first three hits have aged out
    assert lim.hit("a") and lim.count("a") == 1
    lim.reset("a")
    assert lim.count("a") == 0


def test_a_blocked_attempt_does_not_extend_the_block(clock):
    lim = SlidingWindowLimiter(2, 10, clock)
    lim.hit("k"), lim.hit("k")
    for _ in range(50):
        clock.advance(0.1)
        assert not lim.hit("k")
    clock.advance(6)  # 11 seconds since the first two hits
    assert lim.hit("k")


# ---------------- headers and size ----------------
def test_api_responses_carry_security_headers(client):
    for r in (client.get("/health"), client.get("/auth/me"), client.get("/no/such/route")):
        h = r.headers
        assert h["x-content-type-options"] == "nosniff" and h["cache-control"] == "no-store"
        assert h["referrer-policy"] == "no-referrer" and h["x-frame-options"] == "DENY"
        assert "default-src 'none'" in h["content-security-policy"]
        assert "camera=()" in h["permissions-policy"]
    assert "content-security-policy" not in client.get("/docs").headers  # Swagger needs its scripts


def test_oversized_bodies_are_refused(client):
    big = "x" * (settings.MAX_BODY_BYTES + 10)
    r = client.post("/auth/login", content=big, headers={"content-type": "application/json"})
    assert r.status_code == 413 and r.headers["x-content-type-options"] == "nosniff"

    def chunks():  # no Content-Length: sent in pieces
        for _ in range(settings.MAX_BODY_BYTES // 1000 + 5):
            yield b"y" * 1000

    assert (
        client.post(
            "/auth/login", content=chunks(), headers={"content-type": "application/json"}
        ).status_code
        == 413
    )
    assert (
        client.post("/auth/login", json={"username": "a", "password": "b"}).status_code == 401
    )  # normal size still works


def test_login_inputs_have_length_limits(client):
    assert (
        client.post("/auth/login", json={"username": "a" * 65, "password": "x"}).status_code == 422
    )
    assert (
        client.post("/auth/login", json={"username": "a", "password": "x" * 257}).status_code == 422
    )
    assert client.post("/auth/login", json={"username": "", "password": "x"}).status_code == 422


# ---------------- login lockout ----------------
def login(client, name, pw):
    return client.post("/auth/login", json={"username": name, "password": pw})


def test_repeated_failures_lock_that_account_and_address_then_recover(
    client, person, rate_limits_on, clock, staff_tokens
):
    pid, name = person
    rate_limits_on.configure("login_failures", 3, 900, clock)
    assert [login(client, name, "wrong").status_code for _ in range(3)] == [401, 401, 401]
    locked = login(client, name, "correct horse battery")  # even the right password is refused now
    assert locked.status_code == 429 and int(locked.headers["retry-after"]) > 0
    assert (
        login(client, "someone_else", "wrong").status_code == 401
    )  # other accounts are not locked out
    clock.advance(901)
    ok = login(client, name, "correct horse battery")
    assert ok.status_code == 200 and parse_token(ok.json()["token"]) == pid
    # a good sign-in clears the count
    assert [login(client, name, "wrong").status_code for _ in range(2)] == [401, 401]
    assert login(client, name, "correct horse battery").status_code == 200
    assert login(client, name, "wrong").status_code == 401

    entries = client.get("/audit?limit=500", headers=staff_tokens["auditor"]).json()
    locks = [e for e in entries if e["action"] == "login_locked" and e["target_id"] == name]
    assert (
        len(locks) == 1 and locks[0]["reason_code"] == "LOGIN_LOCKED"
    )  # one entry per lockout, not per attempt
    assert any(e["action"] == "login" and e["actor_id"] == pid for e in entries)


def test_unknown_usernames_lock_the_same_way(client, rate_limits_on, clock):
    rate_limits_on.configure("login_failures", 2, 900, clock)
    assert [login(client, "nobody_here", "x").status_code for _ in range(2)] == [401, 401]
    assert (
        login(client, "nobody_here", "x").status_code == 429
    )  # cannot tell a real username from a made-up one


def test_login_attempts_per_address_are_limited(client, rate_limits_on, clock):
    rate_limits_on.configure("login_attempts_ip", 3, 60, clock)
    rate_limits_on.configure("login_failures", 100, 900, clock)
    codes = [login(client, f"user{i}", "x").status_code for i in range(5)]
    assert codes == [401, 401, 401, 429, 429]
    clock.advance(61)
    assert login(client, "user9", "x").status_code == 401


def test_device_and_staff_requests_are_rate_limited(
    client, kiosk, staff_tokens, rate_limits_on, clock
):
    rid, token, _ = kiosk()
    rate_limits_on.configure("device", 3, 60, clock)
    codes = [
        client.get("/device/view", headers={"X-Device-Token": token}).status_code for _ in range(5)
    ]
    assert codes == [200, 200, 200, 429, 429]
    rate_limits_on.configure("staff", 2, 60, clock)
    codes = [client.get("/auth/me", headers=staff_tokens["officer"]).status_code for _ in range(4)]
    assert codes == [200, 200, 429, 429]
    assert client.get("/auth/me", headers=staff_tokens["admin"]).status_code == 200  # per person
    rate_limits_on.configure("ip", 2, 60, clock)
    assert [
        client.get("/auth/me", headers=staff_tokens["auditor"]).status_code for _ in range(3)
    ] == [200, 200, 429]


# ---------------- tokens, refresh, SSO ----------------
def test_tampered_deactivated_and_expired_tokens_are_rejected(client, person, owner_engine):
    pid, name = person
    good = make_token(pid)
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {good}"}).status_code == 200
    body, _, sig = good.partition(".")
    flipped = body + "." + ("0" if sig[0] != "0" else "1") + sig[1:]
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {flipped}"}).status_code == 401
    other = make_token(pid + 100000)  # a valid signature for someone who does not exist
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {other}"}).status_code == 401
    assert (
        client.get(
            "/auth/me", headers={"Authorization": f"Bearer {make_token(pid, ttl=-1)}"}
        ).status_code
        == 401
    )
    with Session(owner_engine) as s, s.begin():
        s.get(Staff, pid).active = False
    assert (
        client.get("/auth/me", headers={"Authorization": f"Bearer {good}"}).status_code == 401
    )  # takes effect at once


def test_refresh_gives_a_new_working_token_only_to_valid_ones(client, person):
    pid, _ = person
    r = client.post("/auth/refresh", headers={"Authorization": f"Bearer {make_token(pid)}"})
    assert r.status_code == 200 and parse_token(r.json()["token"]) == pid
    assert (
        client.post(
            "/auth/refresh", headers={"Authorization": f"Bearer {make_token(pid, ttl=-5)}"}
        ).status_code
        == 401
    )
    assert client.post("/auth/refresh").status_code == 401


def test_mock_sso(client, person, monkeypatch):
    pid, name = person
    ok = client.post("/auth/sso", json={"assertion": f"mock:{name}"})
    assert ok.status_code == 200 and parse_token(ok.json()["token"]) == pid
    for bad in ("mock:nobody-here", "mock:", "saml:" + name, name):
        assert client.post("/auth/sso", json={"assertion": bad}).status_code == 401
    monkeypatch.setattr(settings, "SSO_MOCK_ENABLED", False)
    assert client.post("/auth/sso", json={"assertion": f"mock:{name}"}).status_code == 404


# ---------------- production settings ----------------
GOOD = dict(
    secret_key="s" * 40,
    salt="p" * 20,
    database_url="postgresql+psycopg://app:x9@db/isd",
    migration_url="postgresql+psycopg://owner:y8@db/isd",
    sso_mock=False,
    research_salt="r" * 20,
)


def test_production_refuses_development_defaults():
    assert settings.validate_for_env("production", **GOOD) == []
    assert settings.validate_for_env("dev") == []  # development is unrestricted
    cases = {
        "secret_key": "dev-only-secret-change-me",
        "salt": "dev-only-public-log-salt-change-me",
        "database_url": "postgresql+psycopg://isd_app:isd_app_dev_only@db/isd",
        "migration_url": "postgresql+psycopg://isd:isd_dev_only@db/isd",
        "sso_mock": True,
    }
    for key, bad in cases.items():
        problems = settings.validate_for_env("production", **{**GOOD, key: bad})
        assert problems, key
    assert settings.validate_for_env("production", **{**GOOD, "secret_key": "short"})
    same = settings.validate_for_env(
        "production", **{**GOOD, "migration_url": GOOD["database_url"]}
    )
    assert any("must be different" in p or "must differ" in p for p in same)


@pytest.mark.asyncio_cfg if False else pytest.mark.filterwarnings("ignore")
def test_the_app_will_not_start_in_production_with_defaults(monkeypatch):
    import asyncio

    from isd.main import lifespan

    async def start():
        async with lifespan(app):
            pass

    monkeypatch.setattr(settings, "ENV", "production")
    with pytest.raises(RuntimeError, match="unsafe production settings"):
        asyncio.run(start())
    monkeypatch.setattr(settings, "ENV", "dev")
    asyncio.run(start())  # fine in development


# ---------------- access control sweeps ----------------
def concrete(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "1", path)


def all_routes():
    for r in iter_api_routes(app):
        if r.path not in PUBLIC:
            for method in sorted(r.methods - {"HEAD", "OPTIONS"}):
                yield r, method


def test_every_protected_route_rejects_anonymous_and_wrong_credential_types(client):
    checked = 0
    for route, method in all_routes():
        url = concrete(route.path)
        anon = client.request(method, url, json={})
        assert anon.status_code == 401, (
            f"{method} {route.path} answered {anon.status_code} to an anonymous caller"
        )
        is_device = any(hasattr(d.call, "device_auth") for d in route.dependant.dependencies)
        if is_device:  # a staff token is not a device token
            r = client.request(
                method, url, json={}, headers={"Authorization": f"Bearer {make_token(1)}"}
            )
        else:  # and a device token is not a staff token
            r = client.request(method, url, json={}, headers={"X-Device-Token": "not-a-token"})
        assert r.status_code == 401, f"{method} {route.path} accepted the wrong kind of credential"
        checked += 1
    assert operations(app) == documented_operations(app)  # we really did sweep every route
    assert checked == len([1 for _ in all_routes()]) > 50


def test_every_staff_route_enforces_its_roles(client, staff_tokens):
    """Each role a route does not allow gets 403, before anything else is looked at."""
    checked = 0
    for route, method in all_routes():
        guard = next(
            (d.call for d in route.dependant.dependencies if hasattr(d.call, "allowed_roles")), None
        )
        if guard is None:
            continue
        for role in ROLES:
            if role in guard.allowed_roles:
                continue
            r = client.request(method, concrete(route.path), json={}, headers=staff_tokens[role])
            assert r.status_code == 403, f"{method} {route.path}: {role} got {r.status_code}"
            checked += 1
    assert checked > 50


def test_cors_is_not_enabled(client):
    r = client.options(
        "/auth/me",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"},
    )
    assert "access-control-allow-origin" not in r.headers
    assert (
        "access-control-allow-origin"
        not in client.get("/health", headers={"Origin": "https://evil.example"}).headers
    )


def test_the_synthetic_seed_refuses_to_run_in_production(owner, monkeypatch):
    from isd.seed_db import seed_database

    monkeypatch.setattr(settings, "ENV", "production")
    with pytest.raises(RuntimeError, match="refusing to load the synthetic seed"):
        seed_database(owner, {"config": {}, "staff": [], "residents": [], "contacts": []})
