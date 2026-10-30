"""Fixes from the independent invariant review (Phase 23)."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from isd.engine.features import BASELINE_FEATURES
from isd.models import AuditLog, CallRecord, Contact, Resident
from isd.services import calls
from isd.services.audit import SYSTEM
from isd.services.config_store import get_current, set_config
from tests.conftest import NOW

# Pinned from CLAUDE.md section 1/2 (plus the owner-approved reentry): the test must not just
# compare the code with itself.
PINNED_BASELINE = {
    "legal_materials", "grievances_appeals", "health_requests",
    "request_staff", "emergency_contact", "religious_texts", "basic_education", "attorney_calls",
    "contact_requests", "out_of_cell_minimum", "reentry",
}  # fmt: skip


@pytest.fixture
def make_resident_committed(owner_engine):
    import uuid

    def _make() -> int:
        with Session(owner_engine) as s, s.begin():
            r = Resident(code=f"RV-{uuid.uuid4().hex[:8]}", display_name="Synthetic")
            s.add(r)
            s.flush()
            return r.id

    return _make


def test_the_protected_baseline_is_exactly_the_agreed_list():
    assert set(BASELINE_FEATURES) == PINNED_BASELINE


def test_config_cannot_make_attorney_calls_monitored_or_zero_the_minimum(owner, seeded):
    comp = dict(get_current(owner, "compliance").payload, privileged_contact_types=[])
    with pytest.raises(ValueError):
        set_config(owner, SYSTEM, "compliance", comp, "try to monitor attorneys")
    tiers = dict(get_current(owner, "tiers").payload, baseline_out_of_cell_minutes=0)
    with pytest.raises(ValueError):
        set_config(owner, SYSTEM, "tiers", tiers, "zero the minimum")
    courses = dict(get_current(owner, "courses").payload, uncapped_attempt_levels=[])
    with pytest.raises(ValueError):
        set_config(owner, SYSTEM, "courses", courses, "cap basic education")


def test_an_attorney_call_ends_a_stale_family_call_instead_of_waiting(owner, seeded, make_resident):
    rid = make_resident()
    family = Contact(resident_id=rid, name="F", type="family", phone_ref="555-0101",
                     approved=True, status="approved")  # fmt: skip
    lawyer = Contact(resident_id=rid, name="L", type="attorney", phone_ref="555-0102",
                     approved=True, status="approved")  # fmt: skip
    owner.add_all([family, lawyer])
    owner.flush()
    first = calls.start_call(owner, rid, family.id, NOW)
    with pytest.raises(calls.CallDenied) as e:
        calls.start_call(owner, rid, family.id, NOW)
    assert e.value.code == "CALL_IN_PROGRESS"
    second = calls.start_call(owner, rid, lawyer.id, NOW)
    assert second.privileged and not second.monitored
    assert owner.get(CallRecord, first.id).status == "completed"


def test_staff_cannot_file_a_system_event_as_evidence(
    client, staff_tokens, make_resident_committed
):
    rid = make_resident_committed()
    r = client.post(
        "/staff/sanctions",
        json={"resident_id": rid, "infraction_code": "DEVICE_TAMPER",
              "evidence": {"type": "system_event", "ref": "made-up"}},
        headers=staff_tokens["officer"],
    )  # fmt: skip
    assert r.status_code == 422 and r.json()["detail"]["code"] == "EVIDENCE_REQUIRED"


def test_a_refused_attorney_recording_is_audited_over_http(
    client, staff_tokens, owner_engine, make_resident_committed
):
    rid = make_resident_committed()
    with Session(owner_engine) as s, s.begin():
        contact = Contact(resident_id=rid, name="L", type="attorney", phone_ref="555-0103",
                          approved=True, status="approved")  # fmt: skip
        s.add(contact)
        s.flush()
        call = CallRecord(resident_id=rid, contact_id=contact.id, contact_type="attorney",
                          privileged=True, monitored=False, provider_ref="mock-x",
                          started_at=NOW, max_seconds=60, status="completed")  # fmt: skip
        s.add(call)
        s.flush()
        call_id = call.id

    def denied():
        with Session(owner_engine) as s:
            return s.execute(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.action == "monitoring_denied")
            ).scalar()

    before = denied()
    r = client.post(
        f"/staff/monitoring/calls/{call_id}/review",
        json={"reason": "checking a call"},
        headers=staff_tokens["supervisor"],
    )
    assert r.status_code == 403
    assert denied() == before + 1  # the refusal is kept even though the request failed


def test_one_noisy_address_cannot_block_request_staff(client, monkeypatch):
    from isd import limits, settings

    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    try:
        limits.configure("ip", 1, 60)
        codes = [client.get("/health").status_code for _ in range(3)]
        assert 429 in codes  # the guard is on...
        assert client.post("/device/requests", json={}).status_code != 429  # ...but not for this
    finally:
        limits.reset_defaults()
