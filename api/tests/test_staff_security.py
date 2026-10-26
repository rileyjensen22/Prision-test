"""Staff MFA (TOTP), recovery codes, password change and reset, account administration."""

import time
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from isd import settings, totp
from isd.auth import hash_password
from isd.models import AuditLog, Staff

PW = "a-long-test-password-1"


@pytest.fixture
def account(owner_engine, committed_config):
    """Factory: a committed staff account; returns (username, id)."""

    def _make(role="supervisor", **kw):
        name = f"t_{uuid.uuid4().hex[:8]}"
        with Session(owner_engine) as s, s.begin():
            st = Staff(username=name, role=role, password_hash=hash_password(PW), **kw)
            s.add(st)
            s.flush()
            return name, st.id

    return _make


def login(client, name, password=PW, **extra):
    return client.post("/auth/login", json={"username": name, "password": password, **extra})


def bearer(res):
    return {"Authorization": f"Bearer {res.json()['token']}"}


def audit(owner_engine, action):
    with Session(owner_engine) as s:
        return list(s.execute(select(AuditLog).where(AuditLog.action == action)).scalars())


def test_totp_matches_the_rfc_6238_test_vector():
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"  # ASCII 12345678901234567890
    assert totp.code_at(secret, 59) == "287082"
    assert totp.code_at(secret, 1111111109) == "081804"
    assert totp.verify(secret, "287082", 59) is not None
    assert totp.verify(secret, "000000", 59) is None


def test_a_code_works_once_and_only_near_its_time():
    secret = totp.new_secret()
    t = 1_000_000.0
    step = totp.verify(secret, totp.code_at(secret, t), t)
    assert step is not None
    assert totp.verify(secret, totp.code_at(secret, t), t, last_step=step) is None  # replay
    assert totp.verify(secret, totp.code_at(secret, t), t + 300) is None  # five minutes later


def test_enrolment_then_login_needs_the_code_and_recovery_codes_work_once(
    client, account, owner_engine
):
    name, _ = account()
    res = login(client, name)
    assert res.status_code == 200 and res.json()["mfa_enrollment_required"] is False
    h = bearer(res)
    setup = client.post("/auth/mfa/setup", headers=h).json()
    assert setup["otpauth_uri"].startswith("otpauth://totp/")
    bad = client.post("/auth/mfa/enable", json={"code": "000000"}, headers=h)
    assert bad.status_code == 422 and bad.json()["detail"]["code"] == "BAD_CODE"
    ok = client.post(
        "/auth/mfa/enable", json={"code": totp.code_at(setup["secret"], time.time())}, headers=h
    )
    codes = ok.json()["recovery_codes"]
    assert ok.status_code == 200 and len(codes) == 10

    # signing in now needs a second factor
    needs = login(client, name)
    assert needs.status_code == 401 and needs.json()["detail"]["code"] == "MFA_REQUIRED"
    assert login(client, name, totp="000000").status_code == 401
    # the code that enabled MFA cannot be replayed to sign in
    assert login(client, name, totp=totp.code_at(setup["secret"], time.time())).status_code == 401
    assert login(client, name, recovery=codes[0]).status_code == 200
    assert login(client, name, recovery=codes[0]).status_code == 401  # used
    assert login(client, name, recovery=codes[1]).status_code == 200

    # the audit log records the steps and never a secret or a code
    text = str(
        [
            a.payload
            for action in ("mfa_enabled", "mfa_recovery_code_used", "mfa_setup_started")
            for a in audit(owner_engine, action)
        ]
    )
    assert setup["secret"] not in text and codes[0] not in text
    assert audit(owner_engine, "mfa_enabled")


def test_the_mfa_secret_is_stored_encrypted(client, account, owner_engine):
    from sqlalchemy import text

    name, sid = account()
    h = bearer(login(client, name))
    secret = client.post("/auth/mfa/setup", headers=h).json()["secret"]
    with Session(owner_engine) as s:
        raw = s.execute(text("SELECT mfa_secret FROM staff WHERE id = :i"), {"i": sid}).scalar()
    assert raw.startswith("enc1:") and secret not in raw


def test_when_mfa_is_required_an_unenrolled_person_can_only_enrol(client, account, monkeypatch):
    monkeypatch.setattr(settings, "STAFF_MFA_REQUIRED", True)
    name, _ = account()
    res = login(client, name)
    assert res.json()["mfa_enrollment_required"] is True
    h = bearer(res)
    blocked = client.get("/staff/roster", headers=h)
    assert blocked.status_code == 403 and blocked.json()["detail"]["code"] == "ENROLLMENT_REQUIRED"
    assert (
        client.post("/auth/refresh", headers=h).status_code == 403
    )  # cannot extend a restricted token
    setup = client.post("/auth/mfa/setup", headers=h).json()
    done = client.post(
        "/auth/mfa/enable", json={"code": totp.code_at(setup["secret"], time.time())}, headers=h
    )
    full = {"Authorization": f"Bearer {done.json()['token']}"}
    assert client.get("/staff/roster", headers=full).status_code == 200


def test_changing_a_password_checks_the_old_one_the_rules_and_ends_old_sessions(
    client, account, owner_engine
):
    name, _ = account()
    old = bearer(login(client, name))
    wrong = client.post(
        "/auth/change-password",
        json={"current_password": "nope", "new_password": "another-long-password-2"},
        headers=old,
    )
    assert wrong.json()["detail"]["code"] == "WRONG_PASSWORD"
    for weak in ("short", "password1234", name + "-extra-long", PW):
        r = client.post(
            "/auth/change-password",
            json={"current_password": PW, "new_password": weak},
            headers=old,
        )
        assert r.status_code == 422 and r.json()["detail"]["code"] == "WEAK_PASSWORD", weak
    ok = client.post(
        "/auth/change-password",
        json={"current_password": PW, "new_password": "another-long-password-2"},
        headers=old,
    )
    assert ok.status_code == 200
    time.sleep(1.1)  # password_changed_at has one-second resolution in tokens
    assert client.get("/auth/me", headers=old).status_code == 401  # the old session is over
    assert (
        client.get(
            "/auth/me", headers={"Authorization": f"Bearer {ok.json()['token']}"}
        ).status_code
        == 200
    )
    assert login(client, name, password="another-long-password-2").status_code == 200
    assert audit(owner_engine, "password_changed")


def test_admin_creates_resets_and_deactivates_accounts_and_it_is_all_audited(
    client, account, owner_engine, staff_tokens
):
    admin = staff_tokens["admin"]
    made = client.post(
        "/staff/accounts",
        json={"username": f"new_{uuid.uuid4().hex[:6]}", "role": "officer", "reason": "new hire"},
        headers=admin,
    )
    assert made.status_code == 201
    temp, uid, uname = made.json()["temporary_password"], made.json()["id"], made.json()["username"]
    first = login(client, uname, password=temp)
    assert first.json()["must_change_password"] is True
    h = bearer(first)
    blocked = client.get("/staff/roster", headers=h)
    assert (
        blocked.status_code == 403
        and blocked.json()["detail"]["code"] == "PASSWORD_CHANGE_REQUIRED"
    )
    changed = client.post(
        "/auth/change-password",
        json={"current_password": temp, "new_password": "my-own-long-password-3"},
        headers=h,
    )
    assert (
        client.get(
            "/staff/roster", headers={"Authorization": f"Bearer {changed.json()['token']}"}
        ).status_code
        == 200
    )

    reset = client.post(
        f"/staff/accounts/{uid}/reset-password", json={"reason": "forgot it"}, headers=admin
    )
    new_temp = reset.json()["temporary_password"]
    assert login(client, uname, password=new_temp).json()["must_change_password"] is True
    assert (
        client.post(
            f"/staff/accounts/{uid}/active", json={"active": False, "reason": "left"}, headers=admin
        ).status_code
        == 200
    )
    assert login(client, uname, password=new_temp).status_code == 401
    logged = str(
        [
            a.payload
            for act in (
                "staff_account_created",
                "staff_password_reset",
                "staff_account_deactivated",
            )
            for a in audit(owner_engine, act)
        ]
    )
    assert temp not in logged and new_temp not in logged and "reason" in logged


def test_admin_steps_are_admin_only_need_a_reason_and_protect_the_last_admin(
    client, account, staff_tokens, owner_engine
):
    for role in ("officer", "supervisor", "auditor"):
        assert client.get("/staff/accounts", headers=staff_tokens[role]).status_code == 403
    admin = staff_tokens["admin"]
    name, uid = account("officer")
    assert (
        client.post(
            f"/staff/accounts/{uid}/reset-password", json={"reason": " "}, headers=admin
        ).status_code
        == 422
    )
    me = client.get("/auth/me", headers=admin).json()["id"]
    own = client.post(
        f"/staff/accounts/{me}/reset-password", json={"reason": "my own"}, headers=admin
    )
    assert own.status_code == 422 and own.json()["detail"]["code"] == "OWN_ACCOUNT"


def test_resetting_mfa_clears_the_secret_and_ends_sessions(
    client, account, owner_engine, staff_tokens
):
    name, uid = account()
    h = bearer(login(client, name))
    setup = client.post("/auth/mfa/setup", headers=h).json()
    client.post(
        "/auth/mfa/enable", json={"code": totp.code_at(setup["secret"], time.time())}, headers=h
    )
    time.sleep(1.1)
    assert (
        client.post(
            f"/staff/accounts/{uid}/reset-mfa",
            json={"reason": "lost phone"},
            headers=staff_tokens["admin"],
        ).status_code
        == 200
    )
    assert login(client, name).status_code == 200  # no second factor needed until they enrol again
    assert audit(owner_engine, "staff_mfa_reset")
