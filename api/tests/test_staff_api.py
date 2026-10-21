import uuid

import pytest
from sqlalchemy.orm import Session

from isd.auth import make_token
from isd.engine.ceiling import ceiling_tier
from isd.models import Staff

pytestmark = pytest.mark.usefixtures("committed_config")


def dh(token):
    return {"X-Device-Token": token}


@pytest.fixture
def account(owner_engine):
    """Factory: a committed staff account of a role -> (id, auth headers)."""

    def _make(role):
        with Session(owner_engine) as s, s.begin():
            st = Staff(username=f"{role}_{uuid.uuid4().hex[:8]}", role=role, password_hash="x")
            s.add(st)
            s.flush()
            return st.id, {"Authorization": f"Bearer {make_token(st.id)}"}

    return _make


def test_full_sanction_to_appeal_flow(client, kiosk, account, staff_tokens):
    rid, token, _ = kiosk()
    officer_id, officer = account("officer")
    colleague_id, _ = account("officer")
    sup1_id, sup1 = account("supervisor")
    sup2_id, sup2 = account("supervisor")

    # evidence is mandatory, and must come from a second person
    r = client.post(
        "/staff/sanctions",
        json={"resident_id": rid, "infraction_code": "CAM_BLOCK"},
        headers=officer,
    )
    assert r.status_code == 409 and r.json()["detail"]["code"] == "EVIDENCE_REQUIRED"
    selfie = {"type": "second_staff_report", "reporter_id": officer_id}
    r = client.post(
        "/staff/sanctions",
        json={"resident_id": rid, "infraction_code": "CAM_BLOCK", "evidence": selfie},
        headers=officer,
    )
    assert r.status_code == 409

    for bogus in (0, 99999999):  # not a real staff member
        ghost = {"type": "second_staff_report", "reporter_id": bogus}
        r = client.post(
            "/staff/sanctions",
            json={"resident_id": rid, "infraction_code": "CAM_BLOCK", "evidence": ghost},
            headers=officer,
        )
        assert r.status_code == 409 and r.json()["detail"]["code"] == "EVIDENCE_REQUIRED"

    ev = {"type": "second_staff_report", "reporter_id": colleague_id}
    issued = client.post(
        "/staff/sanctions",
        json={"resident_id": rid, "infraction_code": "CAM_BLOCK", "evidence": ev},
        headers=officer,
    )
    assert issued.status_code == 201 and issued.json()["status"] == "pending"
    sid = issued.json()["id"]
    assert client.get("/device/view", headers=dh(token)).json()["locks"] == []  # nothing locked yet

    # the queue is for supervisors (and read-only roles), not officers
    assert client.get("/staff/confirmations", headers=officer).status_code == 403
    queue = client.get("/staff/confirmations", headers=sup1).json()
    item = next(q for q in queue if q["id"] == sid)
    assert item["can_confirm"] is True and item["issued_by"]["id"] == officer_id
    assert item["evidence"]["reporter"]["id"] == colleague_id and item["why_pending"]
    assert client.post(f"/staff/sanctions/{sid}/confirm", headers=officer).status_code == 403

    confirmed = client.post(f"/staff/sanctions/{sid}/confirm", headers=sup1)
    assert confirmed.status_code == 200 and confirmed.json()["status"] == "active"
    again = client.post(f"/staff/sanctions/{sid}/confirm", headers=sup2)
    assert again.status_code == 409 and again.json()["detail"]["code"] == "NOT_PENDING"

    view = client.get("/device/view", headers=dh(token)).json()
    assert [lock["code"] for lock in view["locks"]] == ["CAM_BLOCK"]
    assert (
        not view["features"]["calls"]["allowed"] and view["features"]["legal_materials"]["allowed"]
    )

    assert (
        client.post("/device/appeals", json={"sanction_id": sid}, headers=dh(token)).status_code
        == 201
    )
    appeals = client.get("/staff/appeals", headers=sup2).json()
    appeal = next(a for a in appeals if a["sanction_id"] == sid)
    assert appeal["can_review"] is True and appeal["overdue"] is False

    bad = {"outcome": "overturned", "note": "  "}
    assert (
        client.post(
            f"/staff/appeals/{appeal['appeal_id']}/review", json=bad, headers=sup2
        ).status_code
        == 422
    )
    body = {"outcome": "overturned", "note": "camera was bumped, not covered"}
    assert (
        client.post(
            f"/staff/appeals/{appeal['appeal_id']}/review", json=body, headers=officer
        ).status_code
        == 403
    )
    done = client.post(f"/staff/appeals/{appeal['appeal_id']}/review", json=body, headers=sup2)
    assert done.status_code == 200 and done.json()["status"] == "overturned"

    after = client.get("/device/view", headers=dh(token)).json()
    assert after["locks"] == [] and after["features"]["calls"]["allowed"]
    detail = client.get(f"/staff/residents/{rid}", headers=sup1).json()
    assert detail["sanctions"][0]["status"] == "overturned" and detail["points"] == 0

    feed = client.get("/staff/events?limit=100", headers=officer).json()
    actions = [e["action"] for e in feed if e["target"] == detail["code"]]
    assert {"sanction_issued", "sanction_confirmed", "appeal_filed", "appeal_reviewed"} <= set(
        actions
    )
    assert client.get("/audit/verify", headers=staff_tokens["auditor"]).json()["ok"] is True
    _ = sup1_id, sup2_id


def test_supervisor_cannot_confirm_or_review_their_own_sanction(client, kiosk, account):
    rid, token, _ = kiosk()
    colleague_id, _ = account("officer")
    sup_id, sup = account("supervisor")
    _, other_sup = account("supervisor")
    ev = {"type": "second_staff_report", "reporter_id": colleague_id}
    sid = client.post(
        "/staff/sanctions",
        json={"resident_id": rid, "infraction_code": "DEVICE_DAMAGE", "evidence": ev},
        headers=sup,
    ).json()["id"]
    item = next(q for q in client.get("/staff/confirmations", headers=sup).json() if q["id"] == sid)
    assert item["can_confirm"] is False
    r = client.post(f"/staff/sanctions/{sid}/confirm", headers=sup)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "SAME_PERSON"
    assert client.post(f"/staff/sanctions/{sid}/confirm", headers=other_sup).status_code == 200

    client.post("/device/appeals", json={"sanction_id": sid}, headers=dh(token))
    appeal = next(
        a for a in client.get("/staff/appeals", headers=sup).json() if a["sanction_id"] == sid
    )
    assert appeal["can_review"] is False
    body = {"outcome": "upheld", "note": "stands"}
    r = client.post(f"/staff/appeals/{appeal['appeal_id']}/review", json=body, headers=sup)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "SAME_PERSON"
    assert (
        client.post(
            f"/staff/appeals/{appeal['appeal_id']}/review", json=body, headers=other_sup
        ).status_code
        == 200
    )


def test_reject_needs_a_note_and_clears_the_queue(client, kiosk, account):
    rid, token, _ = kiosk()
    colleague_id, _ = account("officer")
    _, officer = account("officer")
    _, sup = account("supervisor")
    ev = {"type": "second_staff_report", "reporter_id": colleague_id}
    sid = client.post(
        "/staff/sanctions",
        json={"resident_id": rid, "infraction_code": "CAM_BLOCK", "evidence": ev},
        headers=officer,
    ).json()["id"]
    assert (
        client.post(f"/staff/sanctions/{sid}/reject", json={"note": " "}, headers=sup).status_code
        == 422
    )
    assert (
        client.post(
            f"/staff/sanctions/{sid}/reject", json={"note": "insufficient evidence"}, headers=sup
        ).json()["status"]
        == "rejected"
    )
    assert all(q["id"] != sid for q in client.get("/staff/confirmations", headers=sup).json())
    assert client.get("/device/view", headers=dh(token)).json()["locks"] == []


def test_minor_sanction_is_immediate_and_system_cap_applies(client, kiosk, account):
    rid, token, _ = kiosk()
    _, officer = account("officer")
    r = client.post(
        "/staff/sanctions", json={"resident_id": rid, "infraction_code": "DISRUPT"}, headers=officer
    )
    assert r.json()["status"] == "active"
    assert (
        client.post(
            "/staff/sanctions",
            json={"resident_id": rid, "infraction_code": "NOPE"},
            headers=officer,
        ).status_code
        == 409
    )
    for role_headers in (account("auditor")[1], account("admin")[1]):
        assert (
            client.post(
                "/staff/sanctions",
                json={"resident_id": rid, "infraction_code": "DISRUPT"},
                headers=role_headers,
            ).status_code
            == 403
        )


def test_roster_shows_tier_sanctions_and_sync(client, kiosk, account):
    rid, token, _ = kiosk(prior_returns=10)
    _, officer = account("officer")
    _, aud = account("auditor")
    row = next(
        r for r in client.get("/staff/roster", headers=aud).json() if r["resident_id"] == rid
    )
    assert row["offline"] is True and row["last_sync_at"] is None  # never synced
    assert row["tier"]["ceiling"] == 2 and row["pending_sanctions"] == 0
    client.get("/device/view", headers=dh(token))  # device checks in
    client.post(
        "/staff/sanctions",
        json={"resident_id": rid, "infraction_code": "CELL_MESS"},
        headers=officer,
    )
    row = next(
        r for r in client.get("/staff/roster", headers=aud).json() if r["resident_id"] == rid
    )
    assert row["offline"] is False and row["last_sync_at"]
    assert [s["code"] for s in row["active_sanctions"]] == ["CELL_MESS"]
    assert client.get("/staff/roster").status_code == 401


def test_summary_and_outliers_visibility(client, account):
    _, officer = account("officer")
    _, sup = account("supervisor")
    assert client.get("/staff/outliers", headers=officer).status_code == 403
    out = client.get("/staff/outliers", headers=sup).json()
    assert set(out["groups"]) == {"officer", "supervisor"} and out["settings"]["z_threshold"] == 2.0
    s_off = client.get("/staff/summary", headers=officer).json()
    s_sup = client.get("/staff/summary", headers=sup).json()
    assert s_off["outlier_flags"] is None and isinstance(s_sup["outlier_flags"], int)
    assert {"residents", "pending_confirmations", "open_appeals", "offline_devices"} <= set(s_sup)


def test_ceiling_preview_uses_the_engine(client, account):
    _, officer = account("officer")
    rows = client.get("/staff/ceiling-preview?N=12&p=1.5", headers=officer).json()
    assert [r["ceiling_tier"] for r in rows[1:13]] == [10, 9, 9, 8, 7, 6, 6, 5, 4, 2, 1, 1]
    assert rows[0]["returns"] == 0 and rows[0]["ceiling_tier"] == 10
    custom = client.get("/staff/ceiling-preview?N=6&p=2", headers=officer).json()
    assert all(r["ceiling_tier"] == ceiling_tier(r["returns"], 6, 2) for r in custom)
    assert client.get("/staff/ceiling-preview?N=0&p=2", headers=officer).status_code == 422


def test_lookup_endpoints(client, account, staff_tokens):
    _, officer = account("officer")
    codes = {i["code"] for i in client.get("/staff/infractions", headers=officer).json()}
    assert "CAM_BLOCK" in codes and "DISRUPT" in codes
    people = client.get("/staff/colleagues", headers=officer).json()
    assert people and all("password_hash" not in p for p in people)
    sections = {s["name"] for s in client.get("/config", headers=officer).json()}
    assert {"tiers", "sanctions", "courses", "commissary"} <= sections
    assert client.get("/staff/residents/99999999", headers=officer).status_code == 404
