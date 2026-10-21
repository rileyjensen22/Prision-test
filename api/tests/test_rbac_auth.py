from fastapi.routing import APIRoute

from isd.main import app

PUBLIC = {"/health", "/auth/login", "/openapi.json", "/docs", "/redoc", "/docs/oauth2-redirect"}


def _has_role_guard(route: APIRoute) -> bool:
    return any(hasattr(d.call, "allowed_roles") for d in route.dependant.dependencies)


def test_every_non_public_route_has_a_role_guard():
    unguarded = [
        r.path
        for r in app.routes
        if isinstance(r, APIRoute) and r.path not in PUBLIC and not _has_role_guard(r)
    ]
    assert unguarded == []


def test_unauthenticated_rejected(client):
    assert client.get("/audit").status_code == 401
    assert client.get("/auth/me", headers={"Authorization": "Bearer junk"}).status_code == 401


def test_login_and_me(client, staff_tokens):
    r = client.post("/auth/login", json={"username": "test_officer", "password": "pw-test"})
    assert r.status_code == 200
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {r.json()['token']}"})
    assert me.json()["role"] == "officer"
    bad = client.post("/auth/login", json={"username": "test_officer", "password": "nope"})
    assert bad.status_code == 401


def test_audit_read_roles(client, staff_tokens):
    for role, expected in [("officer", 403), ("supervisor", 403), ("admin", 200), ("auditor", 200)]:
        assert client.get("/audit", headers=staff_tokens[role]).status_code == expected, role


def test_auditor_is_read_only(client, staff_tokens):
    body = {"payload": {"x": 1}, "reason": "nope"}
    assert (
        client.put("/config/tiers", json=body, headers=staff_tokens["auditor"]).status_code == 403
    )
    corr = {"ref_seq": 1, "reason_code": "X", "note": "n"}
    assert (
        client.post("/audit/corrections", json=corr, headers=staff_tokens["auditor"]).status_code
        == 403
    )


def test_expired_token_rejected(client, staff_tokens):
    from isd.auth import make_token

    assert (
        client.get(
            "/auth/me", headers={"Authorization": f"Bearer {make_token(1, ttl=-5)}"}
        ).status_code
        == 401
    )
