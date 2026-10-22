import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from isd.auth import make_token
from isd.models import Cell, Contact, Staff
from isd.services import points
from isd.services.audit import SYSTEM

pytestmark = pytest.mark.usefixtures("committed_config", "committed_reference")


DARK = {"signal": "dark", "covered_ms": 3000}


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


@pytest.fixture
def boost(owner_engine):
    def _boost(rid, pts):
        with Session(owner_engine) as s, s.begin():
            points.record_points(
                s,
                SYSTEM,
                rid,
                "seed_adjustment",
                pts,
                "system",
                datetime.now(UTC) - timedelta(days=1),
            )
            points.evaluate_tier(s, rid, datetime.now(UTC))

    return _boost


@pytest.fixture
def contact(owner_engine):
    def _make(rid, type_="family", name="Synthetic Contact"):
        with Session(owner_engine) as s, s.begin():
            c = Contact(resident_id=rid, name=name, type=type_, phone_ref="555-0123")
            s.add(c)
            s.flush()
            return c.id

    return _make


# ---------------- resident-side stubs over HTTP ----------------
def test_texting_over_http(client, kiosk, boost, contact):
    rid, token, _ = kiosk()
    family, attorney = contact(rid), contact(rid, "attorney")
    assert (
        client.post(
            "/device/messages", json={"contact_id": family, "body": "hi"}, headers=dh(token)
        ).json()["detail"]["code"]
        == "FEATURE_LOCKED"
    )
    boost(rid, 450)
    ok = client.post(
        "/device/messages", json={"contact_id": family, "body": "hello"}, headers=dh(token)
    )
    assert ok.status_code == 201 and ok.json() == {
        "id": ok.json()["id"],
        "private": False,
        "monitored": True,
        "delivery": "delivered",
    }
    thread = client.get(f"/device/messages?contact_id={family}", headers=dh(token)).json()
    assert [m["direction"] for m in thread] == ["out", "in"] and thread[0]["body"] == "hello"
    p = client.post(
        "/device/messages",
        json={"contact_id": attorney, "body": "private words"},
        headers=dh(token),
    )
    assert p.json()["private"] is True and p.json()["monitored"] is False
    assert [
        m["body"]
        for m in client.get(f"/device/messages?contact_id={attorney}", headers=dh(token)).json()
    ] == [None]
    view = client.get("/device/view", headers=dh(token)).json()
    assert next(a for a in view["allowances"] if a["feature"] == "texting")["used"] == 2
    assert (
        client.post(
            "/device/messages", json={"contact_id": family, "body": "x" * 5000}, headers=dh(token)
        ).status_code
        == 422
    )
    assert client.get(f"/device/messages?contact_id={family}").status_code == 401


def test_video_and_tamper_over_http(client, kiosk, boost, contact, account):
    rid, token, _ = kiosk()
    boost(rid, 1000)
    cid = contact(rid)
    v = client.post("/device/video-calls", json={"contact_id": cid}, headers=dh(token))
    assert v.status_code == 201 and v.json()["max_seconds"] == 30 * 60
    t = client.post(
        f"/device/video-calls/{v.json()['call_id']}/tamper", json=DARK, headers=dh(token)
    )
    assert t.status_code == 200 and t.json()["status"] == "pending"
    again = client.post(
        f"/device/video-calls/{v.json()['call_id']}/tamper", json=DARK, headers=dh(token)
    )
    assert again.json()["sanction_id"] == t.json()["sanction_id"]
    _, sup = account("supervisor")
    queue = client.get("/staff/confirmations", headers=sup).json()
    item = next(q for q in queue if q["id"] == t.json()["sanction_id"])
    assert item["infraction_code"] == "DEVICE_TAMPER" and item["issued_by"] is None
    assert item["evidence"]["type"] == "system_event" and item["can_confirm"] is True
    assert (
        client.post("/device/video-calls/999999/tamper", json=DARK, headers=dh(token)).status_code
        == 404
    )


def test_chess_reading_rec_over_http(client, kiosk, boost):
    rid, token, _ = kiosk()
    boost(rid, 100)
    assert (
        client.post("/device/chess", json={"opponent": "human"}, headers=dh(token)).status_code
        == 409
    )
    g = client.post("/device/chess", json={"opponent": "engine"}, headers=dh(token)).json()
    moved = client.post(
        f"/device/chess/{g['id']}/moves", json={"move": "e2e4"}, headers=dh(token)
    ).json()
    assert [m["by"] for m in moved["moves"]] == ["resident", "opponent"]
    assert (
        client.post(
            f"/device/chess/{g['id']}/moves", json={"move": "nonsense"}, headers=dh(token)
        ).status_code
        == 409
    )
    assert len(client.get("/device/chess", headers=dh(token)).json()) == 1

    items = {i["id"]: i for i in client.get("/device/reading", headers=dh(token)).json()}
    assert items["tortoise-hare"]["allowed"] and not items["gettysburg"]["allowed"]
    assert (
        client.get("/device/reading/tortoise-hare", headers=dh(token))
        .json()["text"]
        .startswith("A hare")
    )
    assert client.get("/device/reading/gettysburg", headers=dh(token)).status_code == 409
    assert client.get("/device/reading/nope", headers=dh(token)).status_code == 404

    day = client.get("/device/rec", headers=dh(token)).json()
    assert day["baseline_minutes"] == 60 and {s["kind"] for s in day["slots"]} == {
        "indoor",
        "outdoor",
        "program",
        "visit",
    }
    book = {"day": day["day"], "slot": "09:00"}
    assert client.post("/device/rec/book", json=book, headers=dh(token)).status_code == 201
    assert client.post("/device/rec/book", json=book, headers=dh(token)).status_code == 409
    assert (
        client.post(
            "/device/rec/book", json={**book, "slot": "10:00"}, headers=dh(token)
        ).status_code
        == 409
    )  # outdoor
    assert client.post("/device/rec/cancel", json=book, headers=dh(token)).json() == {
        "cancelled": True
    }


def test_jobs_over_http_are_voluntary_and_private_to_the_resident(client, kiosk, account):
    rid, token, _ = kiosk()
    body = client.get("/device/jobs", headers=dh(token)).json()
    assert body["pay_split"] == {"resident_pct": 60, "facility_pct": 30, "deductions_pct": 10}
    job = body["jobs"][0]
    assert job["enrolled"] is False
    before = client.get("/device/view", headers=dh(token)).json()
    assert client.post(f"/device/jobs/{job['id']}/join", headers=dh(token)).status_code == 201
    assert client.post(f"/device/jobs/{job['id']}/join", headers=dh(token)).status_code == 409
    assert client.get("/device/jobs", headers=dh(token)).json()["jobs"][0]["enrolled"] is True
    assert client.post(f"/device/jobs/{job['id']}/leave", headers=dh(token)).json() == {
        "joined": False
    }
    assert client.post(f"/device/jobs/{job['id']}/leave", headers=dh(token)).status_code == 409
    after = client.get("/device/view", headers=dh(token)).json()
    for k in ("tier", "features", "locks", "allowances"):
        assert before[k] == after[k]  # nothing about the resident changed

    _, sup = account("supervisor")
    listing = client.get("/staff/jobs", headers=sup).json()
    assert all(
        set(j)
        == {"id", "code", "title", "task_type", "active", "participants", "pay_per_task_cents"}
        for j in listing
    )  # no resident info


# ---------------- staff side ----------------
def test_out_of_cell_and_welfare_endpoints(client, kiosk, account, staff_tokens):
    rid, token, _ = kiosk()
    _, officer = account("officer")
    today = datetime.now(UTC).date()
    ok = {"resident_id": rid, "day": today.isoformat(), "minutes": 30}
    assert (
        client.post("/staff/out-of-cell", json=ok, headers=staff_tokens["auditor"]).status_code
        == 403
    )
    assert client.post("/staff/out-of-cell", json=ok).status_code == 401
    assert client.post("/staff/out-of-cell", json=ok, headers=officer).status_code == 201
    assert (
        client.post("/staff/out-of-cell", json={**ok, "minutes": 5000}, headers=officer).status_code
        == 422
    )
    assert (
        client.post(
            "/staff/out-of-cell",
            json={**ok, "day": (today + timedelta(days=2)).isoformat()},
            headers=officer,
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/staff/out-of-cell", json={**ok, "resident_id": 99999999}, headers=officer
        ).status_code
        == 404
    )
    window = client.get(
        f"/staff/residents/{rid}/out-of-cell?days=3", headers=staff_tokens["auditor"]
    ).json()
    assert window[-1] == {"day": today.isoformat(), "minutes": 30} and len(window) == 3

    flags = client.get("/staff/welfare", headers=staff_tokens["auditor"]).json()
    mine = next((f for f in flags if f["resident_id"] == rid), None)
    assert mine is None or all(
        f["type"] != "no_contact" for f in mine["flags"]
    )  # brand-new resident
    summary = client.get("/staff/summary", headers=officer).json()
    assert isinstance(summary["welfare_flags"], int)
    ack = {"resident_id": rid, "flag_type": "no_contact", "note": "Checked in on them"}
    assert (
        client.post("/staff/welfare/ack", json=ack, headers=staff_tokens["auditor"]).status_code
        == 403
    )
    assert (
        client.post("/staff/welfare/ack", json={**ack, "note": "x"}, headers=officer).status_code
        == 422
    )
    # a brand-new resident has no open flag to acknowledge
    none = client.post("/staff/welfare/ack", json=ack, headers=officer)
    assert none.status_code == 409 and none.json()["detail"]["code"] == "NO_OPEN_FLAG"


def test_timeline_endpoint_roles_and_logging(client, kiosk, account, staff_tokens):
    rid, _, _ = kiosk()
    _, officer = account("officer")
    _, sup = account("supervisor")
    url = f"/staff/residents/{rid}/timeline"
    assert client.get(url + "?reason=curious", headers=officer).status_code == 403
    assert client.get(url).status_code == 401
    assert client.get(url + "?reason=no", headers=sup).status_code == 409
    assert client.get(url + "?reason=quarterly review of activity", headers=sup).status_code == 200
    assert (
        client.get(
            "/staff/residents/99999999/timeline?reason=quarterly review", headers=sup
        ).status_code
        == 404
    )
    entries = client.get("/audit?limit=500", headers=staff_tokens["auditor"]).json()
    assert any(
        e["action"] == "monitoring_access"
        and e["payload"].get("reason") == "quarterly review of activity"
        for e in entries
    )


def test_content_sources_and_job_admin_are_admin_only_and_audited(client, account, staff_tokens):
    _, sup = account("supervisor")
    _, admin = account("admin")
    src = {
        "name": f"Library {uuid.uuid4().hex[:6]}",
        "kind": "external",
        "base_url": "https://library.example",
    }
    assert client.post("/staff/content-sources", json=src, headers=sup).status_code == 403
    sid = client.post("/staff/content-sources", json=src, headers=admin).json()["id"]
    assert (
        client.post(
            "/staff/content-sources",
            json={**src, "name": "Insecure source", "base_url": "http://x.example"},
            headers=admin,
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/staff/content-sources/{sid}/active", json={"active": False}, headers=admin
        ).json()["active"]
        is False
    )
    assert any(s["id"] == sid for s in client.get("/staff/content-sources", headers=sup).json())

    job = {
        "code": f"J{uuid.uuid4().hex[:5]}",
        "title": "Label shapes",
        "task_type": "labeling_non_personal",
        "description": "Sort images of shapes",
    }
    assert client.post("/staff/jobs", json=job, headers=sup).status_code == 403
    assert (
        client.post(
            "/staff/jobs",
            json={**job, "code": "BADTYPE", "task_type": "customer_support"},
            headers=admin,
        ).status_code
        == 422
    )
    jid = client.post("/staff/jobs", json=job, headers=admin).json()["id"]
    assert (
        client.post(f"/staff/jobs/{jid}/active", json={"active": False}, headers=admin).json()[
            "active"
        ]
        is False
    )
    actions = {
        e["action"] for e in client.get("/audit?limit=500", headers=staff_tokens["auditor"]).json()
    }
    assert {
        "content_source_added",
        "content_source_changed",
        "job_listing_created",
        "job_listing_changed",
    } <= actions


def test_facility_events_over_http(client, kiosk, account, owner_engine):
    rid, token, device = kiosk()
    cell = "C-" + device[2:]
    _, sup = account("supervisor")
    _, admin = account("admin")
    ev = {
        "event_id": f"evt-{uuid.uuid4().hex[:10]}",
        "type": "camera_obstruction",
        "payload": {"cell": cell},
    }
    assert client.post("/mock/facility-events", json=ev, headers=sup).status_code == 403
    first = client.post("/mock/facility-events", json=ev, headers=admin)
    second = client.post("/mock/facility-events", json=ev, headers=admin)
    assert (
        first.status_code == 201
        and first.json() == second.json()
        and first.json()["result"].endswith(":pending")
    )
    view = client.get("/device/view", headers=dh(token)).json()
    assert view["locks"] == []  # pending until a supervisor confirms
    item = next(
        q
        for q in client.get("/staff/confirmations", headers=sup).json()
        if q["resident_code"]
        and q["infraction_code"] == "CAM_BLOCK"
        and q["evidence"]["ref"] == ev["event_id"]
    )
    assert (
        client.post(f"/staff/sanctions/{item['id']}/confirm", headers=sup).json()["status"]
        == "active"
    )
    assert client.get("/device/view", headers=dh(token)).json()["locks"][0]["code"] == "CAM_BLOCK"
    _ = Cell
