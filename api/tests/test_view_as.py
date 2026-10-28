import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import InternalError, ProgrammingError
from sqlalchemy.orm import Session

from isd.auth import make_token
from isd.engine.sandbox import SandboxOverrides, SandboxSanction
from isd.models import Base, Contact, MirrorSession, PointEvent, Staff
from isd.services import sanctions
from isd.services.audit import Actor, verify_chain
from isd.services.resident_view import build_resident_view

pytestmark = pytest.mark.usefixtures("committed_config")


def dh(token):
    return {"X-Device-Token": token}


@pytest.fixture
def account(owner_engine):
    def _make(role):
        with Session(owner_engine) as s, s.begin():
            st = Staff(username=f"{role}_{uuid.uuid4().hex[:8]}", role=role, password_hash="x")
            s.add(st)
            s.flush()
            return st.id, {"Authorization": f"Bearer {make_token(st.id)}"}

    return _make


def table_fingerprints(engine) -> dict[str, str]:
    """A checksum of every table's full contents, so any insert, update or delete shows up."""
    out = {}
    with engine.connect() as c:
        for t in Base.metadata.sorted_tables:
            sql = (
                "SELECT md5(coalesce(string_agg(x::text, '|' ORDER BY x::text), '')) "
                f'FROM "{t.name}" x'
            )
            out[t.name] = c.execute(text(sql)).scalar()
    return out


def sandbox(client, headers, rid, overrides=None, at_time=None):
    body = {"resident_id": rid, "overrides": overrides or {}}
    if at_time:
        body["at_time"] = at_time.isoformat()
    return client.post("/staff/sandbox/view", json=body, headers=headers)


# ======================= sandbox =======================
def test_sandbox_makes_zero_writes_across_many_requests(
    client, kiosk, account, owner_engine, staff_tokens
):
    rid, token, _ = kiosk()
    _, officer = account("officer")
    client.get("/device/view", headers=dh(token))  # settle the device's own sync timestamp first
    before = table_fingerprints(owner_engine)
    now = datetime.now(UTC)
    requests = [
        {},
        {"tier": 9, "language": "es", "text_size": "xlarge"},
        {"prior_returns": 12},
        {"offense_categories": ["PLACEHOLDER_CATEGORY_A", "PLACEHOLDER_CATEGORY_B"]},
        {"add_sanctions": [{"code": "CAM_BLOCK", "hours_remaining": 5}, {"code": "DISRUPT"}]},
        {"clear_sanctions": True, "tier": 3, "captions": True},
        {"tier": 99},  # invalid -> 422
        {"add_sanctions": [{"code": "NOPE"}]},  # invalid -> 422
    ]
    statuses = [sandbox(client, officer, rid, o).status_code for o in requests]
    assert statuses == [200] * 6 + [422, 422]
    sandbox(client, officer, rid, {"tier": 7}, at_time=now + timedelta(days=30))
    sandbox(client, officer, rid, {}, at_time=now - timedelta(days=400))
    assert sandbox(client, officer, 99999999).status_code == 404
    assert sandbox(client, staff_tokens["auditor"], rid, {"tier": 2}).status_code == 200
    assert before == table_fingerprints(owner_engine)  # not one row changed
    assert verify_chain(Session(owner_engine)).ok


def test_the_database_refuses_writes_inside_the_sandbox_transaction(client, kiosk, app_engine):
    """Zero writes is enforced by Postgres (READ ONLY transaction), not just by careful code."""
    from isd.db import get_readonly_db

    rid, _, _ = kiosk()
    gen = get_readonly_db()
    session = next(gen)
    try:
        view = build_resident_view(
            session,
            rid,
            datetime.now(UTC),
            simulation=True,
            overrides=SandboxOverrides(tier=5, add_sanctions=(SandboxSanction("DISRUPT"),)),
        )
        assert view.simulation and view.tier.effective == 5
        session.add(PointEvent(resident_id=rid, kind="x", points=1, source="staff"))
        with pytest.raises((InternalError, ProgrammingError), match="read-only"):
            session.flush()
    finally:
        gen.close()


def test_sandbox_applies_overrides_through_the_real_engine(client, kiosk, account):
    rid, _, _ = kiosk()
    _, officer = account("officer")
    v = sandbox(client, officer, rid, {"tier": 6, "language": "es", "text_size": "large"}).json()
    assert v["simulation"] is True
    assert v["tier"]["effective"] == 6 and v["tier"]["points"] == 1000
    assert v["tier"]["next_tier"] == 7 and v["tier"]["points_to_next"] == 400
    assert v["features"]["calls"]["limits"] == {"minutes_per_day": 45}
    assert v["features"]["video"]["allowed"] and v["settings"]["language"] == "es"
    assert v["settings"]["text_size"] == "large"

    v = sandbox(client, officer, rid, {"tier": 10, "prior_returns": 10}).json()  # ceiling 2
    assert v["tier"]["effective"] == 2 and v["tier"]["capped_by_ceiling"] is True
    assert v["features"]["texting"]["reasons"][0]["code"] == "TIER_CEILING"

    v = sandbox(
        client, officer, rid, {"add_sanctions": [{"code": "CAM_BLOCK", "hours_remaining": 3}]}
    ).json()
    (lock,) = v["locks"]
    assert lock["code"] == "CAM_BLOCK" and lock["sanction_id"] is not None
    assert not v["features"]["calls"]["allowed"] and v["features"]["legal_materials"]["allowed"]
    assert (
        v["features"]["attorney_calls"]["allowed"] and v["features"]["basic_education"]["allowed"]
    )
    ends = datetime.fromisoformat(lock["ends_at"])
    assert timedelta(hours=2.9) < ends - datetime.now(UTC) < timedelta(hours=3.1)

    v = sandbox(
        client, officer, rid, {"offense_categories": ["PLACEHOLDER_CATEGORY_A"], "tier": 8}
    ).json()
    assert v["features"]["video"]["reasons"][0]["code"] == "OFFENSE_RESTRICTION"


def test_sandbox_matches_the_real_view_when_nothing_is_overridden(
    client, kiosk, account, owner_engine
):
    rid, token, _ = kiosk()
    _, sup = account("supervisor")
    with Session(owner_engine) as s, s.begin():
        sanctions.issue_sanction(
            s, Actor(account("officer")[0], "officer"), rid, "DISRUPT", datetime.now(UTC)
        )
    at = datetime.now(UTC)
    with Session(owner_engine) as s:
        real = build_resident_view(s, rid, at).model_dump(mode="json")
    sim = sandbox(client, sup, rid, at_time=at).json()
    assert sim.pop("simulation") is True and real.pop("simulation") is False
    assert sim == real


def test_time_travel_shows_past_and_future_locks(client, kiosk, account, owner_engine):
    rid, _, _ = kiosk()
    _, officer = account("officer")
    now = datetime.now(UTC)
    issued = now - timedelta(days=3)
    with Session(owner_engine) as s, s.begin():
        sanctions.issue_sanction(s, Actor(account("officer")[0], "officer"), rid, "DISRUPT", issued)
    during = sandbox(client, officer, rid, at_time=issued + timedelta(hours=2)).json()
    assert [lock["code"] for lock in during["locks"]] == ["DISRUPT"]
    assert sandbox(client, officer, rid).json()["locks"] == []  # it ended two days ago
    far = sandbox(client, officer, rid, at_time=now + timedelta(days=10)).json()
    assert far["locks"] == []
    assert sandbox(client, officer, rid, at_time=now + timedelta(days=800)).status_code == 422


def test_sandbox_requires_a_staff_login(client, kiosk):
    rid, token, _ = kiosk()
    assert client.post("/staff/sandbox/view", json={"resident_id": rid}).status_code == 401
    assert (
        client.post("/staff/sandbox/view", json={"resident_id": rid}, headers=dh(token)).status_code
        == 401
    )


# ======================= live mirror =======================
@pytest.fixture
def contact(owner_engine):
    def _make(rid, type_="family"):
        with Session(owner_engine) as s, s.begin():
            c = Contact(resident_id=rid, name="Synthetic Contact", type=type_, phone_ref="555-0110")
            s.add(c)
            s.flush()
            return c.id

    return _make


def start(client, headers, rid, reason="welfare check requested by shift lead"):
    return client.post(
        "/staff/mirror/sessions", json={"resident_id": rid, "reason": reason}, headers=headers
    )


def audit_actions(client, staff_tokens):
    return client.get("/audit?limit=500", headers=staff_tokens["auditor"]).json()


def test_mirror_session_lifecycle_is_fully_logged(client, kiosk, account, staff_tokens):
    rid, token, _ = kiosk()
    sup_id, sup = account("supervisor")
    assert start(client, sup, rid, reason="no").status_code == 409
    sid = start(client, sup, rid).json()["session_id"]

    assert (
        client.post(
            "/device/screen", json={"path": "/resident/tier"}, headers=dh(token)
        ).status_code
        == 204
    )
    frame = client.get(f"/staff/mirror/sessions/{sid}/frame", headers=sup).json()
    assert frame["redacted"] is None and frame["screen"]["path"] == "/resident/tier"
    assert frame["view"]["tier"]["effective"] == 1 and frame["view"]["simulation"] is False

    client.post("/device/screen", json={"path": "/resident"}, headers=dh(token))
    assert (
        client.get(f"/staff/mirror/sessions/{sid}/frame", headers=sup).json()["screen"]["path"]
        == "/resident"
    )

    ended = client.post(f"/staff/mirror/sessions/{sid}/end", headers=sup).json()
    assert ended["ended"] and ended["end_reason"] == "manual"
    assert client.get(f"/staff/mirror/sessions/{sid}/frame", headers=sup).status_code == 410

    entries = [
        e for e in audit_actions(client, staff_tokens) if e["payload"].get("session_id") == sid
    ]
    assert [e["action"] for e in entries] == ["mirror_started", "mirror_ended"]
    started, finished = entries
    assert started["actor_id"] == sup_id and started["actor_role"] == "supervisor"
    assert started["payload"]["reason"] == "welfare check requested by shift lead"
    assert started["target_id"] == str(rid) and started["reason_code"] == "MIRROR_START"
    assert finished["reason_code"] == "MIRROR_END" and finished["payload"]["frames"] == 2
    assert client.get("/audit/verify", headers=staff_tokens["auditor"]).json()["ok"]


def test_mirror_access_rules(client, kiosk, account, staff_tokens):
    rid, token, _ = kiosk()
    _, officer = account("officer")
    _, sup = account("supervisor")
    _, other_sup = account("supervisor")
    _, admin = account("admin")
    assert start(client, officer, rid).status_code == 403
    assert start(client, staff_tokens["auditor"], rid).status_code == 403
    assert (
        client.post(
            "/staff/mirror/sessions", json={"resident_id": rid, "reason": "check it"}
        ).status_code
        == 401
    )
    assert start(client, sup, 99999999).status_code == 404
    sid = start(client, sup, rid).json()["session_id"]
    assert client.get(f"/staff/mirror/sessions/{sid}/frame", headers=other_sup).status_code == 404
    assert client.get(f"/staff/mirror/sessions/{sid}/frame", headers=admin).status_code == 200
    assert client.get(f"/staff/mirror/sessions/{sid}/frame", headers=officer).status_code == 403
    mine = {s["id"] for s in client.get("/staff/mirror/sessions", headers=sup).json()}
    theirs = {s["id"] for s in client.get("/staff/mirror/sessions", headers=other_sup).json()}
    everyone = {
        s["id"]
        for s in client.get("/staff/mirror/sessions", headers=staff_tokens["auditor"]).json()
    }
    assert sid in mine and sid not in theirs and sid in everyone
    assert client.get("/staff/mirror/sessions", headers=officer).status_code == 403


def test_mirror_needs_an_assigned_device(client, account, owner_engine):
    from isd.models import Resident

    with Session(owner_engine) as s, s.begin():
        r = Resident(code=f"R-{uuid.uuid4().hex[:8]}", display_name="Synthetic")
        s.add(r)
        s.flush()
        rid = r.id
    _, sup = account("supervisor")
    r = start(client, sup, rid)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "NO_DEVICE"


def test_private_screens_are_never_mirrored(client, kiosk, account):
    rid, token, _ = kiosk()
    _, sup = account("supervisor")
    sid = start(client, sup, rid).json()["session_id"]
    for path in (
        "/resident/feature/legal_materials",
        "/resident/feature/health_requests",
        "/resident/feature/grievances_appeals/new",
    ):
        client.post("/device/screen", json={"path": path}, headers=dh(token))
        f = client.get(f"/staff/mirror/sessions/{sid}/frame", headers=sup).json()
        assert f["redacted"] == "PRIVATE_SCREEN" and f["view"] is None and f["screen"] is None
        assert path not in str(f)


def test_mirror_hides_everything_during_an_attorney_call(client, kiosk, account, contact):
    rid, token, _ = kiosk()
    _, sup = account("supervisor")
    attorney, family = contact(rid, "attorney"), contact(rid, "family")
    sid = start(client, sup, rid).json()["session_id"]
    client.post("/device/screen", json={"path": "/resident/feature/calls"}, headers=dh(token))
    assert client.get(f"/staff/mirror/sessions/{sid}/frame", headers=sup).json()["redacted"] is None

    call = client.post("/device/calls", json={"contact_id": attorney}, headers=dh(token)).json()
    f = client.get(f"/staff/mirror/sessions/{sid}/frame", headers=sup).json()
    assert f["redacted"] == "PRIVILEGED_CALL" and f["view"] is None and f["screen"] is None
    client.post(f"/device/calls/{call['call_id']}/end", headers=dh(token))
    assert client.get(f"/staff/mirror/sessions/{sid}/frame", headers=sup).json()["redacted"] is None

    regular = client.post("/device/calls", json={"contact_id": family}, headers=dh(token)).json()
    assert client.get(f"/staff/mirror/sessions/{sid}/frame", headers=sup).json()["redacted"] is None
    client.post(f"/device/calls/{regular['call_id']}/end", headers=dh(token))


def test_device_never_stores_private_screen_paths(client, kiosk, owner_engine):
    from isd.models import Device

    rid, token, code = kiosk()
    client.post(
        "/device/screen", json={"path": "/resident/feature/legal_materials"}, headers=dh(token)
    )
    with Session(owner_engine) as s:
        assert (
            s.execute(select(Device.current_screen).where(Device.code == code)).scalar()
            == "/resident/redacted"
        )
    for bad in ("/staff", "/resident?x=1", "/resident/../a", "http://evil"):
        assert (
            client.post("/device/screen", json={"path": bad}, headers=dh(token)).status_code == 422
        )
    assert client.post("/device/screen", json={"path": "/resident"}).status_code == 401


def test_mirror_sessions_expire_and_the_expiry_is_logged(
    client, kiosk, account, owner_engine, staff_tokens
):
    rid, token, _ = kiosk()
    _, sup = account("supervisor")
    idle_id = start(client, sup, rid).json()["session_id"]
    long_id = start(client, sup, rid).json()["session_id"]
    now = datetime.now(UTC)
    with Session(owner_engine) as s, s.begin():
        s.get(MirrorSession, idle_id).last_seen_at = now - timedelta(minutes=5)
        old = s.get(MirrorSession, long_id)
        old.started_at, old.last_seen_at = now - timedelta(minutes=30), now
    assert client.get(f"/staff/mirror/sessions/{idle_id}/frame", headers=sup).status_code == 410
    assert client.get(f"/staff/mirror/sessions/{long_id}/frame", headers=sup).status_code == 410
    with Session(owner_engine) as s:
        assert s.get(MirrorSession, idle_id).end_reason == "idle"
        assert s.get(MirrorSession, long_id).end_reason == "timeout"
    ended = {
        e["payload"]["session_id"]: e
        for e in audit_actions(client, staff_tokens)
        if e["action"] == "mirror_ended"
    }
    assert (
        ended[idle_id]["reason_code"] == "MIRROR_IDLE"
        and ended[long_id]["reason_code"] == "MIRROR_TIMEOUT"
    )
    assert ended[long_id]["payload"]["seconds"] == 15 * 60  # capped at the limit


def test_mirror_frames_do_not_change_resident_data(client, kiosk, account, owner_engine):
    rid, token, _ = kiosk()
    _, sup = account("supervisor")
    client.get("/device/view", headers=dh(token))
    sid = start(client, sup, rid).json()["session_id"]
    watched = (
        "point_events",
        "sanctions",
        "appeals",
        "trust_ledger",
        "call_records",
        "tier_history",
        "residents",
        "contacts",
        "staff_requests",
        "commissary_orders",
    )
    before = {k: v for k, v in table_fingerprints(owner_engine).items() if k in watched}
    for _ in range(5):
        client.get(f"/staff/mirror/sessions/{sid}/frame", headers=sup)
    assert before == {k: v for k, v in table_fingerprints(owner_engine).items() if k in watched}
