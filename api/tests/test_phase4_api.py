from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from isd import providers
from isd.models import CallRecord, Contact
from isd.services import commissary, points
from isd.services.audit import SYSTEM
from tests.helpers import quiz_answers

pytestmark = pytest.mark.usefixtures("committed_config")
ANSWERS = [0, 1, 0, 1, 0]


def hdr(token):
    return {"X-Device-Token": token}


@pytest.fixture
def contact(owner_engine):
    def _make(rid, type_="family", blocked=False):
        with Session(owner_engine) as s, s.begin():
            c = Contact(
                resident_id=rid,
                name="Synthetic Contact",
                type=type_,
                blocked=blocked,
                phone_ref="555-0101",
            )
            s.add(c)
            s.flush()
            return c.id

    return _make


def test_education_demo_loop_over_http(client, kiosk, owner_engine):
    rid, token, _ = kiosk()
    with Session(owner_engine) as s, s.begin():
        points.record_points(s, SYSTEM, rid, "seed_adjustment", 60, "system", datetime.now(UTC))
        points.evaluate_tier(s, rid, datetime.now(UTC))
    before = client.get("/device/view", headers=hdr(token)).json()
    assert before["tier"]["effective"] == 1
    assert next(a for a in before["allowances"] if a["feature"] == "calls")["limit"] == 15

    courses = client.get("/device/courses", headers=hdr(token)).json()
    allowed = {c["code"]: c["allowed"] for c in courses}
    assert allowed["MONEY101"] and allowed["LIT101"] and allowed["NUM101"]  # basic: open to all
    assert not allowed["WORKMATH"] and not allowed["JOBS101"]  # advanced, with prerequisites
    course = client.get("/device/courses/MONEY101", headers=hdr(token)).json()
    assert "answer" not in str(course)
    assert client.get("/device/courses/WORKMATH", headers=hdr(token)).status_code == 409
    early = client.post("/device/courses/MONEY101/quiz/start", headers=hdr(token))
    assert early.status_code == 409 and early.json()["detail"]["code"] == "LESSONS_INCOMPLETE"
    for lesson in course["lessons"]:
        r = client.post(
            f"/device/courses/MONEY101/lessons/{lesson['id']}/complete", headers=hdr(token)
        )
        assert r.status_code == 200
    paper = client.post("/device/courses/MONEY101/quiz/start", headers=hdr(token)).json()
    assert "answer" not in str(paper) and len(paper["questions"]) == 5
    with Session(owner_engine) as s:
        answers = quiz_answers(s, paper["quiz_id"], "MONEY101")
    bad = client.post(
        "/device/courses/MONEY101/quiz", json={"quiz_id": paper["quiz_id"]}, headers=hdr(token)
    )
    assert bad.status_code == 422
    res = client.post(
        "/device/courses/MONEY101/quiz",
        json={"quiz_id": paper["quiz_id"], "answers": answers},
        headers=hdr(token),
    )
    assert res.status_code == 200 and res.json()["passed"]
    assert res.json()["calls_minutes_before"] == 15 and res.json()["calls_minutes_after"] == 20
    assert res.json()["certificate"].startswith("MONEY101-")

    after = client.get("/device/view", headers=hdr(token)).json()
    assert after["tier"]["effective"] == 2
    assert next(a for a in after["allowances"] if a["feature"] == "calls")["limit"] == 20
    assert client.get("/device/courses/NOPE", headers=hdr(token)).status_code == 404


def test_attorney_call_over_http_leaves_no_content(client, kiosk, contact, owner_engine):
    rid, token, _ = kiosk()
    attorney, family = contact(rid, "attorney"), contact(rid, "family")
    contacts = client.get("/device/contacts", headers=hdr(token)).json()
    assert {c["type"] for c in contacts} == {"attorney", "family"}

    provider = providers.get_telephony()._p
    recorded_before = provider.recordings_created
    started = client.post("/device/calls", json={"contact_id": attorney}, headers=hdr(token))
    assert started.status_code == 201
    body = started.json()
    assert body["privileged"] is True and body["monitored"] is False
    ended = client.post(f"/device/calls/{body['call_id']}/end", headers=hdr(token)).json()
    assert ended["status"] == "completed" and ended["duration_seconds"] is not None
    assert provider.recordings_created == recorded_before  # nothing recorded

    with Session(owner_engine) as s:
        row = s.get(CallRecord, body["call_id"])
        assert (row.privileged, row.monitored, row.monitor_ref) == (True, False, None)

    reg = client.post("/device/calls", json={"contact_id": family}, headers=hdr(token))
    assert reg.json()["monitored"] is True and reg.json()["max_seconds"] == 15 * 60
    client.post(f"/device/calls/{reg.json()['call_id']}/end", headers=hdr(token))
    view = client.get("/device/view", headers=hdr(token)).json()
    calls_used = next(a for a in view["allowances"] if a["feature"] == "calls")["used"]
    assert calls_used in (0, 1)  # a few seconds of regular call round up to at most 1 minute


def test_call_errors_over_http(client, kiosk, contact):
    rid, token, _ = kiosk()
    other_rid, _, _ = kiosk()
    blocked = contact(rid, "friend", blocked=True)
    assert (
        client.post("/device/calls", json={"contact_id": blocked}, headers=hdr(token)).json()[
            "detail"
        ]["code"]
        == "CONTACT_UNAVAILABLE"
    )
    foreign = contact(other_rid)
    assert (
        client.post("/device/calls", json={"contact_id": foreign}, headers=hdr(token)).status_code
        == 409
    )
    listed = client.get("/device/contacts", headers=hdr(token)).json()
    assert listed[0]["available"] is False
    assert client.post("/device/calls/999999/end", headers=hdr(token)).status_code == 404


def test_commissary_over_http_with_mock_deposit(client, kiosk, staff_tokens):
    rid, token, _ = kiosk()
    view = client.get("/device/commissary", headers=hdr(token)).json()
    assert view["balance_cents"] == 0 and view["weekly_limit_cents"] == 2000
    broke = client.post(
        "/device/commissary/orders",
        json={"client_id": "order-http-1", "lines": {"SOAP": 1}},
        headers=hdr(token),
    )
    assert broke.status_code == 409 and broke.json()["detail"]["code"] == "INSUFFICIENT_FUNDS"

    dep = {
        "resident_id": rid,
        "amount_cents": 5000,
        "payer_ref": "family-1",
        "idempotency_key": f"dep-{rid}-0001",
    }
    assert (
        client.post("/mock/deposits", json=dep, headers=staff_tokens["officer"]).status_code == 403
    )
    assert client.post("/mock/deposits", json=dep).status_code == 401
    first = client.post("/mock/deposits", json=dep, headers=staff_tokens["supervisor"])
    second = client.post("/mock/deposits", json=dep, headers=staff_tokens["supervisor"])
    assert first.status_code == second.status_code == 201
    assert first.json() == second.json() and first.json()["balance_cents"] == 5000
    assert (
        client.post(
            "/mock/deposits",
            json={**dep, "amount_cents": 99999999, "idempotency_key": "other-key-1"},
            headers=staff_tokens["admin"],
        ).status_code
        == 422
    )

    order = {"client_id": "order-http-2", "lines": {"SOAP": 2, "PAD": 1}}
    ok = client.post("/device/commissary/orders", json=order, headers=hdr(token))
    assert ok.status_code == 201 and ok.json() == {
        "order_id": ok.json()["order_id"],
        "total_cents": 425,
        "balance_cents": 4575,
    }
    assert (
        client.post("/device/commissary/orders", json=order, headers=hdr(token)).json()["order_id"]
        == ok.json()["order_id"]
    )
    tier_locked = client.post(
        "/device/commissary/orders",
        json={"client_id": "order-http-3", "lines": {"SNACK": 1}},
        headers=hdr(token),
    )
    assert tier_locked.json()["detail"]["code"] == "ITEM_TIER"
    assert (
        client.post(
            "/device/commissary/orders",
            json={"client_id": "order-http-4", "lines": {"SOAP": 99}},
            headers=hdr(token),
        ).json()["detail"]["code"]
        == "BAD_QUANTITY"
    )

    v = client.get("/device/view", headers=hdr(token)).json()
    comm = next(a for a in v["allowances"] if a["feature"] == "commissary")
    assert comm["used"] == 4.25 and comm["limit"] == 20


def test_all_ledgers_consistent_after_http_activity(owner_engine):
    with Session(owner_engine) as s:
        assert commissary.verify_ledgers(s) == []
        assert (
            s.execute(
                select(CallRecord).where(CallRecord.privileged, CallRecord.monitor_ref.is_not(None))
            ).first()
            is None
        )
