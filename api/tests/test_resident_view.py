import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from isd.models import (
    AuditLog,
    Resident,
    StaffRequest,
)
from isd.services import points, sanctions
from isd.services.audit import SYSTEM, Actor, verify_chain
from isd.services.resident_view import build_resident_view

pytestmark = pytest.mark.usefixtures("committed_config")


def hdr(token):
    return {"X-Device-Token": token}


def test_device_auth_required(client, kiosk):
    assert client.get("/device/view").status_code == 401
    assert client.get("/device/view", headers=hdr("nope")).status_code == 401
    _, token, _ = kiosk(assigned=False)
    assert client.get("/device/view", headers=hdr(token)).status_code == 409


def test_new_resident_view(client, kiosk):
    rid, token, _ = kiosk()
    r = client.get("/device/view", headers=hdr(token))
    assert r.status_code == 200
    v = r.json()
    assert v["tier"]["effective"] == 1 and v["tier"]["next_tier"] == 2
    assert v["tier"]["points_to_next"] == 100 and not v["tier"]["capped_by_ceiling"]
    assert v["features"]["calls"]["allowed"] and v["features"]["calls"]["limits"] == {
        "minutes_per_day": 15
    }
    texting = v["features"]["texting"]
    assert not texting["allowed"] and texting["reasons"][0]["code"] == "TIER_LOCKED"
    assert texting["reasons"][0]["params"] == {"tier": 4}
    assert v["features"]["legal_materials"]["baseline"] is True
    assert v["locks"] == []  # "not unlocked yet" is not a restriction
    gen = datetime.fromisoformat(v["generated_at"])
    assert datetime.fromisoformat(v["valid_until"]) == gen + timedelta(minutes=60)
    assert v["ui"]["inactivity_return_home_seconds"] == 90
    assert v["simulation"] is False


def test_sanction_lock_visible_with_reason_end_time_and_valid_until(client, kiosk, owner_engine):
    rid, token, _ = kiosk()
    with Session(owner_engine) as s, s.begin():
        officer = Actor(_staff(s, "officer"), "officer")
        # issued 23.5h ago -> ends in 30 minutes, which is sooner than the 60-minute snapshot TTL
        issued = datetime.now(UTC) - timedelta(hours=23, minutes=30)
        sanc = sanctions.issue_sanction(s, officer, rid, "DISRUPT", issued)
        ends = sanc.ends_at
        sid = sanc.id
    v = client.get("/device/view", headers=hdr(token)).json()
    assert not v["features"]["calls"]["allowed"]
    (lock,) = v["locks"]
    assert lock["code"] == "DISRUPT" and lock["sanction_id"] == sid
    assert set(lock["features"]) == {"calls", "texting", "video"}
    assert lock["how_to_appeal"] == "appeal" and not lock["appeal_open"]
    assert datetime.fromisoformat(lock["ends_at"]) == ends
    assert datetime.fromisoformat(v["valid_until"]) == ends
    assert v["features"]["commissary"]["allowed"] and v["features"]["attorney_calls"]["allowed"]


def _staff(session, role):
    from isd.models import Staff

    st = Staff(username=f"{role}_{uuid.uuid4().hex[:8]}", role=role, password_hash="x")
    session.add(st)
    session.flush()
    return st.id


def test_appeal_from_device(client, kiosk, owner_engine):
    rid, token, _ = kiosk()
    other_rid, other_token, _ = kiosk()
    with Session(owner_engine) as s, s.begin():
        officer = Actor(_staff(s, "officer"), "officer")
        sid = sanctions.issue_sanction(s, officer, rid, "CELL_MESS", datetime.now(UTC)).id
    assert (
        client.post(
            "/device/appeals", json={"sanction_id": sid}, headers=hdr(other_token)
        ).status_code
        == 404
    )
    ok = client.post("/device/appeals", json={"sanction_id": sid}, headers=hdr(token))
    assert ok.status_code == 201
    again = client.post("/device/appeals", json={"sanction_id": sid}, headers=hdr(token))
    assert again.status_code == 409 and again.json()["detail"]["code"] == "DUPLICATE_APPEAL"
    lock = client.get("/device/view", headers=hdr(token)).json()["locks"][0]
    assert lock["appeal_open"] is True


def test_request_staff_is_idempotent_for_offline_replay(client, kiosk, owner_engine):
    rid, token, _ = kiosk()
    body = {"kind": "medical", "client_id": f"c-{uuid.uuid4().hex}"}
    a = client.post("/device/requests", json=body, headers=hdr(token))
    b = client.post("/device/requests", json=body, headers=hdr(token))
    assert a.status_code == b.status_code == 201
    assert b.json()["duplicate"] is True and a.json()["request_id"] == b.json()["request_id"]
    assert (
        client.post(
            "/device/requests", json={**body, "kind": "bogus"}, headers=hdr(token)
        ).status_code
        == 422
    )
    with Session(owner_engine) as s:
        rows = (
            s.execute(select(StaffRequest).where(StaffRequest.resident_id == rid)).scalars().all()
        )
        assert len(rows) == 1


def test_ceiling_shown_on_view(client, kiosk, owner_engine):
    rid, token, _ = kiosk(prior_returns=10)  # ceiling 2
    with Session(owner_engine) as s, s.begin():
        for _ in range(2):
            points.add_point_event(s, SYSTEM, rid, "program_certificate", datetime.now(UTC))
    v = client.get("/device/view", headers=hdr(token)).json()
    t = v["tier"]
    assert t["ceiling"] == 2 and t["earned"] == 3 and t["effective"] == 2
    assert t["capped_by_ceiling"] is True
    assert v["features"]["advanced_education"]["reasons"][0]["code"] == "TIER_CEILING"


def test_simulation_flag_is_the_only_difference(kiosk, owner_engine):
    rid, _, _ = kiosk()
    now = datetime.now(UTC)
    with Session(owner_engine) as s:
        a = build_resident_view(s, rid, now).model_dump()
        b = build_resident_view(s, rid, now, simulation=True).model_dump()
    assert a.pop("simulation") is False and b.pop("simulation") is True
    assert a == b


def test_staff_controls_settings_and_residents_cannot(client, kiosk, staff_tokens, owner_engine):
    rid, token, _ = kiosk()
    body = {"language": "es", "text_size": "large", "reason": "requested at intake"}
    assert (
        client.put(f"/staff/residents/{rid}/settings", json=body, headers=hdr(token)).status_code
        == 401
    )
    assert (
        client.put(
            f"/staff/residents/{rid}/settings", json=body, headers=staff_tokens["auditor"]
        ).status_code
        == 403
    )
    ok = client.put(f"/staff/residents/{rid}/settings", json=body, headers=staff_tokens["officer"])
    assert ok.json()["changed"] == ["language", "text_size"]
    v = client.get("/device/view", headers=hdr(token)).json()
    assert v["settings"]["language"] == "es" and v["settings"]["text_size"] == "large"
    bad = {"language": "fr", "reason": "nope"}
    assert (
        client.put(
            f"/staff/residents/{rid}/settings", json=bad, headers=staff_tokens["officer"]
        ).status_code
        == 422
    )
    with Session(owner_engine) as s:
        entry = (
            s.execute(
                select(AuditLog)
                .where(AuditLog.action == "resident_settings_change")
                .order_by(AuditLog.seq.desc())
            )
            .scalars()
            .first()
        )
        assert entry.payload["changes"]["language"] == {"from": "en", "to": "es"}


def test_device_assignment_change_is_audited(client, kiosk, staff_tokens, owner_engine):
    rid1, token, device_code = kiosk()
    rid2, _, _ = kiosk()
    body = {"device_code": device_code, "resident_id": rid2, "reason": "cell move"}
    assert (
        client.post(
            "/staff/device-assignments", json=body, headers=staff_tokens["officer"]
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/staff/device-assignments", json=body, headers=staff_tokens["supervisor"]
        ).status_code
        == 201
    )
    v = client.get("/device/view", headers=hdr(token)).json()
    with Session(owner_engine) as s:
        res2 = s.get(Resident, rid2)
        assert v["resident_code"] == res2.code
        entry = (
            s.execute(
                select(AuditLog).where(
                    AuditLog.action == "device_assignment", AuditLog.target_id == device_code
                )
            )
            .scalars()
            .one()
        )
        assert entry.payload["from_resident"] == rid1 and entry.payload["to_resident"] == rid2
        assert verify_chain(s).ok
