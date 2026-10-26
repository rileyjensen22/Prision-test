"""Monitored call review (invariants 6 and 16): metadata list, reason-gated, never attorney."""

from datetime import timedelta

import pytest
from sqlalchemy import select

from isd.interfaces.telephony import TelephonyService
from isd.mocks.telephony import MockTelephonyProvider
from isd.models import AuditLog, Contact
from isd.services import calls, monitoring
from tests.conftest import NOW
from tests.test_phase7_services import give


@pytest.fixture
def tel():
    provider = MockTelephonyProvider()
    return TelephonyService(provider), provider


def _call(owner, rid, kind, service, phone):
    c = Contact(
        resident_id=rid,
        name="Synthetic Contact",
        type=kind,
        phone_ref=phone,
        approved=True,
        status="approved",
    )
    owner.add(c)
    owner.flush()
    rec = calls.start_call(owner, rid, c.id, NOW, service)
    calls.end_call(owner, rid, rec.id, NOW + timedelta(minutes=4), service)
    return rec


def test_the_queue_lists_monitored_calls_and_never_attorney_calls(
    owner, seeded, make_resident, tel
):
    service, _ = tel
    rid = make_resident()
    give(owner, rid, 100)
    family = _call(owner, rid, "family", service, "555-0111")
    lawyer = _call(owner, rid, "attorney", service, "555-0112")
    q = monitoring.call_queue(owner)
    ids = {row["call_id"] for row in q}
    assert family.id in ids and lawyer.id not in ids
    row = next(r for r in q if r["call_id"] == family.id)
    assert row["duration_seconds"] == 240 and "audio" not in str(row)


def test_a_review_needs_a_reason_is_logged_and_never_opens_an_attorney_call(
    owner, seeded, make_resident, tel, make_staff
):
    service, _ = tel
    rid = make_resident()
    give(owner, rid, 100)
    family = _call(owner, rid, "family", service, "555-0111")
    lawyer = _call(owner, rid, "attorney", service, "555-0112")
    sup = make_staff("supervisor")
    with pytest.raises(monitoring.MonitoringDenied) as e:
        monitoring.review_call(owner, sup, family.id, "  ", service)
    assert e.value.code == "REASON_REQUIRED"
    out = monitoring.review_call(
        owner, sup, family.id, "checking a complaint about threats", service
    )
    assert out["bytes"] > 0
    entry = (
        owner.execute(
            select(AuditLog)
            .where(AuditLog.action == "monitoring_access")
            .order_by(AuditLog.seq.desc())
        )
        .scalars()
        .first()
    )
    assert entry.payload["reason"] == "checking a complaint about threats"
    assert "audio" not in str(entry.payload)
    with pytest.raises(monitoring.MonitoringDenied) as e:
        monitoring.review_call(owner, sup, lawyer.id, "just looking", service)
    assert e.value.code == "PRIVILEGED_DENIED"
    denied = (
        owner.execute(select(AuditLog).where(AuditLog.action == "monitoring_denied"))
        .scalars()
        .all()
    )
    assert denied and denied[-1].payload == {"call_id": lawyer.id}


def test_officers_and_auditors_cannot_open_a_call(owner, seeded, make_resident, tel, make_staff):
    service, _ = tel
    rid = make_resident()
    give(owner, rid, 100)
    family = _call(owner, rid, "family", service, "555-0111")
    for role in ("officer", "auditor"):
        with pytest.raises(monitoring.MonitoringDenied) as e:
            monitoring.review_call(
                owner, make_staff(role), family.id, "a good enough reason", service
            )
        assert e.value.code == "FORBIDDEN"


def test_routes_are_gated_by_role(client, staff_tokens, committed_config):
    s = staff_tokens
    assert client.get("/staff/monitoring/calls", headers=s["auditor"]).status_code == 200
    assert client.get("/staff/monitoring/calls", headers=s["officer"]).status_code == 403
    for role, expect in (("officer", 403), ("auditor", 403), ("supervisor", 404)):
        r = client.post(
            "/staff/monitoring/calls/999999/review",
            json={"reason": "a good reason"},
            headers=s[role],
        )
        assert r.status_code == expect, role
