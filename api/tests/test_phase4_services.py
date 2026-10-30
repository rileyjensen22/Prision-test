from datetime import timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from isd.engine.calls import CallDenied
from isd.engine.commissary import OrderError
from isd.interfaces.telephony import PrivilegedCommunicationError, TelephonyService
from isd.mocks.telephony import MockTelephonyProvider
from isd.models import CallRecord, Contact, OffenseFlag, TrustLedger
from isd.services import calls, commissary, education, points, sanctions
from isd.services.audit import SYSTEM, verify_chain
from isd.services.education import EducationError
from isd.services.entitlement_service import get_entitlements
from tests.conftest import NOW
from tests.helpers import take_quiz


@pytest.fixture
def tel():
    provider = MockTelephonyProvider()
    return TelephonyService(provider), provider


@pytest.fixture
def add_contact(owner):
    def _add(rid, type_="family", blocked=False, phone="555-0100"):
        c = Contact(
            resident_id=rid, name="Synthetic Contact", type=type_, blocked=blocked, phone_ref=phone
        )
        owner.add(c)
        owner.flush()
        return c.id

    return _add


def give_points(owner, rid, n):
    points.record_points(
        owner, SYSTEM, rid, "seed_adjustment", n, "system", NOW - timedelta(days=1)
    )
    points.evaluate_tier(owner, rid, NOW)


def finish_lessons(owner, rid, code="MONEY101", now=NOW):
    ids = [le["id"] for le in education.get_course(owner, rid, code, now)["lessons"]]
    for lid in ids:
        education.complete_lesson(owner, rid, code, lid, now)


# ======================= education =======================
def test_sample_course_completion_raises_tier_and_call_minutes(owner, seeded, make_resident):
    rid = make_resident()
    give_points(owner, rid, 60)
    assert get_entitlements(owner, rid, NOW).features["calls"].limits["minutes_per_day"] == 15
    finish_lessons(owner, rid)
    r = take_quiz(owner, rid, "MONEY101", NOW)
    assert r["passed"] and r["points_awarded"] == 50
    assert (r["tier_before"], r["tier_after"]) == (1, 2)
    assert (r["calls_minutes_before"], r["calls_minutes_after"]) == (15, 20)
    assert get_entitlements(owner, rid, NOW).features["calls"].limits["minutes_per_day"] == 20
    assert verify_chain(owner).ok


def test_completion_awards_points_only_once(owner, seeded, make_resident):
    rid = make_resident()
    finish_lessons(owner, rid)
    first = take_quiz(owner, rid, "MONEY101", NOW)
    again = take_quiz(owner, rid, "MONEY101", NOW + timedelta(hours=1))
    assert first["points_awarded"] == 50 and again["points_awarded"] == 0
    assert again["already_completed"] is True
    assert points.total_points(owner, rid, NOW + timedelta(days=1)) == 50


def test_quiz_rules(owner, seeded, make_resident):
    rid = make_resident()
    with pytest.raises(EducationError) as e:
        education.start_quiz(owner, rid, "MONEY101", NOW)
    assert e.value.code == "LESSONS_INCOMPLETE"
    finish_lessons(owner, rid)
    paper = education.start_quiz(owner, rid, "MONEY101", NOW)
    with pytest.raises(EducationError) as e:
        education.submit_quiz(owner, rid, "MONEY101", paper["quiz_id"], [0, 0], NOW)
    assert e.value.code == "BAD_ANSWERS"
    fail = take_quiz(owner, rid, "MONEY101", NOW, correct=False)  # resumes the open paper
    assert not fail["passed"] and fail["points_awarded"] == 0
    assert points.total_points(owner, rid, NOW) == 0
    later = NOW + timedelta(minutes=11)  # after the cooldown
    assert take_quiz(owner, rid, "MONEY101", later)["passed"]  # retry works


def test_course_content_never_includes_answers(owner, seeded, make_resident):
    rid = make_resident()
    course = education.get_course(owner, rid, "MONEY101", NOW)
    assert "answer" not in str(course) and "prompt" not in str(course["quiz"])
    finish_lessons(owner, rid)
    paper = education.start_quiz(owner, rid, "MONEY101", NOW)
    assert "answer" not in str(paper) and "order" not in str(paper)


def test_advanced_course_gated_but_basic_is_baseline(owner, seeded, make_resident, make_staff):
    rid = make_resident()
    listing = {c["code"]: c for c in education.list_courses(owner, rid, NOW)}
    assert listing["MONEY101"]["allowed"] and not listing["WORKMATH"]["allowed"]
    assert listing["WORKMATH"]["reasons"][0]["code"] == "TIER_LOCKED"
    with pytest.raises(EducationError) as e:
        education.get_course(owner, rid, "WORKMATH", NOW)
    assert e.value.code == "FEATURE_LOCKED"
    give_points(owner, rid, 300)  # tier 3
    with pytest.raises(EducationError) as e:  # the course it builds on comes first
        education.get_course(owner, rid, "WORKMATH", NOW)
    assert e.value.code == "PREREQ_MISSING"
    finish_lessons(owner, rid, "NUM101")
    assert take_quiz(owner, rid, "NUM101", NOW)["passed"]
    assert education.get_course(owner, rid, "WORKMATH", NOW)["code"] == "WORKMATH"
    # a total lock-out sanction removes advanced education but never basic education
    officer, sup = make_staff("officer"), make_staff("supervisor")
    colleague = make_staff("officer")
    from isd.engine.authority import Evidence

    s = sanctions.issue_sanction(
        owner, officer, rid, "DEVICE_DAMAGE", NOW, Evidence("second_staff_report", colleague.id)
    )
    sanctions.confirm_sanction(owner, sup, s.id, NOW)
    listing = {c["code"]: c for c in education.list_courses(owner, rid, NOW)}
    assert listing["MONEY101"]["allowed"] and not listing["WORKMATH"]["allowed"]
    finish_lessons(owner, rid)  # basic course still works while fully sanctioned
    assert take_quiz(owner, rid, "MONEY101", NOW)["passed"]


# ======================= calls =======================
def test_regular_call_is_monitored_and_metered(owner, seeded, make_resident, add_contact, tel):
    service, provider = tel
    rid = make_resident()
    cid = add_contact(rid, "family")
    c = calls.start_call(owner, rid, cid, NOW, service)
    assert c.monitored and not c.privileged and c.max_seconds == 15 * 60
    assert provider.recordings_created == 1
    done = calls.end_call(owner, rid, c.id, NOW + timedelta(minutes=10), service)
    assert done.duration_seconds == 600 and done.status == "completed" and done.monitor_ref
    second = calls.start_call(owner, rid, cid, NOW + timedelta(minutes=11), service)
    assert second.max_seconds == 300  # 15 minute day, 10 already used
    calls.end_call(owner, rid, second.id, NOW + timedelta(minutes=30), service)  # overran its cap
    assert owner.get(CallRecord, second.id).duration_seconds == 300
    with pytest.raises(CallDenied) as e:
        calls.start_call(owner, rid, cid, NOW + timedelta(minutes=40), service)
    assert e.value.code == "LIMIT_REACHED"
    # next day the allowance resets
    assert calls.start_call(owner, rid, cid, NOW + timedelta(days=1), service).max_seconds == 900


def test_one_call_at_a_time_and_abandoned_calls_time_out(
    owner, seeded, make_resident, add_contact, tel
):
    service, _ = tel
    rid = make_resident()
    cid = add_contact(rid)
    c = calls.start_call(owner, rid, cid, NOW, service)
    with pytest.raises(CallDenied) as e:
        calls.start_call(owner, rid, cid, NOW + timedelta(seconds=30), service)
    assert e.value.code == "CALL_IN_PROGRESS"
    later = NOW + timedelta(hours=2)  # device never reported the end
    calls.start_call(owner, rid, add_contact(rid), later + timedelta(days=1), service)
    assert owner.get(CallRecord, c.id).status == "timed_out"
    assert owner.get(CallRecord, c.id).duration_seconds == 900


def test_attorney_calls_are_never_recorded_or_content_logged(
    owner, seeded, make_resident, add_contact, tel, make_staff
):
    service, provider = tel
    rid = make_resident()
    cid = add_contact(rid, "attorney", phone="555-0199")
    c = calls.start_call(owner, rid, cid, NOW, service)
    assert c.privileged and not c.monitored
    done = calls.end_call(owner, rid, c.id, NOW + timedelta(minutes=5), service)
    assert done.duration_seconds == 300  # that a call happened, and how long, may be kept
    assert done.monitor_ref is None
    assert provider.recordings_created == 0  # provider was told not to record, and did not
    assert all(call["monitoring_ref"] is None for call in provider.calls.values())
    # No path back to content, even for a supervisor
    sup = make_staff("supervisor")
    with pytest.raises(PrivilegedCommunicationError):
        calls.fetch_recording(owner, sup, c.id, "reviewing a complaint", service)
    with pytest.raises(PrivilegedCommunicationError):
        service.recording(
            __import__("isd.interfaces.telephony", fromlist=["CallHandle"]).CallHandle(
                c.provider_ref, True
            )
        )
    # The audit trail records the denied attempt without any content
    entry = owner.execute(
        text("SELECT payload, reason_code FROM audit_log WHERE action = 'monitoring_denied'")
    ).one()
    assert entry.reason_code == "PRIVILEGED_DENIED" and entry.payload == {"call_id": c.id}


def test_no_content_columns_exist_for_calls():
    cols = {c.name for c in CallRecord.__table__.columns}
    assert not cols & {"transcript", "recording", "content", "audio", "notes", "summary"}


def test_database_refuses_privileged_calls_with_monitoring(
    owner, seeded, make_resident, add_contact
):
    rid = make_resident()
    cid = add_contact(rid, "attorney")
    base = dict(
        resident_id=rid,
        contact_id=cid,
        contact_type="attorney",
        provider_ref="x",
        started_at=NOW,
        max_seconds=60,
    )
    for bad in (
        dict(privileged=True, monitored=True),
        dict(privileged=True, monitored=False, monitor_ref="mon-1"),
    ):
        with owner.begin_nested():
            owner.add(CallRecord(**base, **bad))
            with pytest.raises(IntegrityError):
                owner.flush()


def test_misbehaving_provider_cannot_capture_attorney_calls(
    owner, seeded, make_resident, add_contact
):
    bad = MockTelephonyProvider(ignore_no_record=True)
    service = TelephonyService(bad)
    rid = make_resident()
    cid = add_contact(rid, "attorney")
    with pytest.raises(PrivilegedCommunicationError):
        calls.start_call(owner, rid, cid, NOW, service)
    assert all(c["ended"] for c in bad.calls.values())  # the guard hung up


def test_attorney_calls_survive_locks_and_do_not_use_allowance(
    owner, seeded, make_resident, add_contact, tel, make_staff
):
    service, _ = tel
    rid = make_resident()
    reg, att = add_contact(rid), add_contact(rid, "attorney")
    s = sanctions.issue_sanction(
        owner, make_staff("officer"), rid, "DISRUPT", NOW
    )  # locks communication
    with pytest.raises(CallDenied) as e:
        calls.start_call(owner, rid, reg, NOW, service)
    assert e.value.code == "FEATURE_LOCKED"
    a = calls.start_call(owner, rid, att, NOW, service)
    calls.end_call(owner, rid, a.id, NOW + timedelta(minutes=50), service)
    assert s.status == "active"
    from isd.services.usage import call_seconds_today

    assert call_seconds_today(owner, rid, NOW + timedelta(minutes=60)) == 0


def test_contact_level_blocks(owner, seeded, make_resident, add_contact, tel):
    service, _ = tel
    rid = make_resident()
    blocked = add_contact(rid, "friend", blocked=True)
    blocked_attorney = add_contact(rid, "attorney", blocked=True)
    with pytest.raises(CallDenied) as e:
        calls.start_call(owner, rid, blocked, NOW, service)
    assert e.value.code == "CONTACT_UNAVAILABLE"
    assert calls.start_call(owner, rid, blocked_attorney, NOW, service).privileged  # baseline wins
    other = make_resident()
    with pytest.raises(CallDenied):
        calls.start_call(owner, other, add_contact(rid), NOW, service)  # not their contact


def test_monitored_call_content_access_is_audited_and_role_limited(
    owner, seeded, make_resident, add_contact, tel, make_staff
):
    service, _ = tel
    rid = make_resident()
    c = calls.start_call(owner, rid, add_contact(rid), NOW, service)
    calls.end_call(owner, rid, c.id, NOW + timedelta(minutes=1), service)
    with pytest.raises(PermissionError):
        calls.fetch_recording(owner, make_staff("officer"), c.id, "reviewing a complaint", service)
    with pytest.raises(PermissionError):  # invariant 16: a stated reason is required
        calls.fetch_recording(owner, make_staff("supervisor"), c.id, "  ", service)
    assert (
        calls.fetch_recording(
            owner, make_staff("supervisor"), c.id, "reviewing a complaint", service
        )
        == b"[synthetic audio]"
    )
    row = owner.execute(
        text(
            "SELECT reason_code, payload FROM audit_log"
            " WHERE action = 'monitoring_access' AND target_type = 'call' AND target_id = :c"
        ),
        {"c": str(c.id)},
    ).one()
    assert row.reason_code == "MONITORING_ACCESS"
    assert row.payload["reason"] == "reviewing a complaint"


# ======================= commissary =======================
def fund(owner, rid, cents=10000, key=None):
    return commissary.deposit(
        owner, SYSTEM, rid, cents, "payer-1", key or f"key-{rid}-{cents}-{NOW}", NOW
    )


def test_deposit_is_idempotent_and_bounded(owner, seeded, make_resident):
    rid = make_resident()
    a = commissary.deposit(owner, SYSTEM, rid, 5000, "p", "idem-key-1", NOW)
    b = commissary.deposit(owner, SYSTEM, rid, 5000, "p", "idem-key-1", NOW)
    assert a.id == b.id and commissary.balance_cents(owner, rid) == 5000
    for bad in (0, -5, 10**6):
        with pytest.raises(OrderError):
            commissary.deposit(owner, SYSTEM, rid, bad, "p", f"k-{bad}-aaaa", NOW)


def test_order_flow_limits_and_idempotency(owner, seeded, make_resident):
    rid = make_resident()
    fund(owner, rid)
    o = commissary.place_order(owner, rid, {"SOAP": 2, "PAD": 1}, "order-aaaa-1", NOW)  # $4.25
    assert o.total_cents == 425 and commissary.balance_cents(owner, rid) == 10000 - 425
    again = commissary.place_order(owner, rid, {"SOAP": 2, "PAD": 1}, "order-aaaa-1", NOW)
    assert (
        again.id == o.id and commissary.balance_cents(owner, rid) == 10000 - 425
    )  # no double charge
    # T1 weekly limit is $20.00: 1575 cents left this week
    commissary.place_order(
        owner, rid, {"STAMPS": 1, "TOOTHPASTE": 3}, "order-aaaa-2", NOW
    )  # 800 + 630
    with pytest.raises(OrderError) as e:
        commissary.place_order(owner, rid, {"STAMPS": 1}, "order-aaaa-3", NOW)
    assert e.value.code == "WEEKLY_LIMIT"
    commissary.place_order(
        owner, rid, {"STAMPS": 1}, "order-aaaa-4", NOW + timedelta(days=8)
    )  # new week
    assert commissary.verify_ledgers(owner) == []


def test_insufficient_funds(owner, seeded, make_resident):
    rid = make_resident()
    fund(owner, rid, 300)
    with pytest.raises(OrderError) as e:
        commissary.place_order(owner, rid, {"PAD": 2}, "order-aaaa-5", NOW)
    assert e.value.code == "INSUFFICIENT_FUNDS"
    assert commissary.balance_cents(owner, rid) == 300


def test_item_restrictions_by_tier_and_offense(owner, seeded, make_resident):
    rid = make_resident()
    fund(owner, rid, 40000)
    with pytest.raises(OrderError) as e:
        commissary.place_order(owner, rid, {"SNACK": 1}, "order-aaaa-6", NOW)
    assert e.value.code == "ITEM_TIER"
    give_points(owner, rid, 450)  # tier 4: headphones allowed by tier
    view = commissary.catalog_view(owner, rid, NOW)
    assert {i["code"]: i["available"] for i in view["items"]}["HEADPHONES"] is True
    owner.add(
        OffenseFlag(
            resident_id=rid,
            offense_category="SEX_OFFENSE",
            added_at=NOW - timedelta(days=1),
        )
    )
    owner.flush()
    view = commissary.catalog_view(owner, rid, NOW)
    hp = next(i for i in view["items"] if i["code"] == "HEADPHONES")
    assert not hp["available"] and hp["block_reason"] == "ITEM_OFFENSE"
    with pytest.raises(OrderError) as e:
        commissary.place_order(owner, rid, {"HEADPHONES": 1}, "order-aaaa-7", NOW)
    assert e.value.code == "ITEM_OFFENSE"
    commissary.place_order(owner, rid, {"SNACK": 1}, "order-aaaa-8", NOW)  # other items unaffected


def test_commissary_sanction_locks_orders_but_not_other_features(
    owner, seeded, make_resident, make_staff
):
    rid = make_resident()
    fund(owner, rid)
    sanctions.issue_sanction(owner, make_staff("officer"), rid, "CELL_MESS", NOW)
    with pytest.raises(OrderError) as e:
        commissary.place_order(owner, rid, {"SOAP": 1}, "order-aaaa-9", NOW + timedelta(hours=1))
    assert e.value.code == "FEATURE_LOCKED"
    assert get_entitlements(owner, rid, NOW + timedelta(hours=1)).allowed("calls")
    commissary.place_order(owner, rid, {"SOAP": 1}, "order-aaaa-10", NOW + timedelta(hours=25))


def test_ledger_tampering_is_detected(owner, seeded, make_resident):
    rid = make_resident()
    fund(owner, rid)
    commissary.place_order(owner, rid, {"SOAP": 1}, "order-aaaa-11", NOW)
    assert commissary.verify_ledgers(owner) == []
    owner.execute(text("ALTER TABLE trust_ledger DISABLE TRIGGER trust_ledger_no_update_delete"))
    owner.execute(
        text(
            "UPDATE trust_ledger SET balance_after_cents = balance_after_cents + 500 "
            "WHERE resident_id = :r AND amount_cents < 0"
        ),
        {"r": rid},
    )
    assert commissary.verify_ledgers(owner)  # the inconsistency is reported
    owner.rollback()


def test_ledger_is_append_only_even_for_the_owner(owner_engine):
    import uuid

    from isd.models import Resident

    with Session(owner_engine) as s, s.begin():
        r = Resident(code=f"R-{uuid.uuid4().hex[:8]}", display_name="Synthetic")
        s.add(r)
        s.flush()
        rid = r.id
        s.add(
            TrustLedger(
                resident_id=rid,
                entry_type="deposit",
                amount_cents=1,
                balance_after_cents=1,
                created_at=NOW,
            )
        )
    for stmt in (
        "UPDATE trust_ledger SET memo = 'x' WHERE resident_id = :r",
        "DELETE FROM trust_ledger WHERE resident_id = :r",
    ):
        with owner_engine.connect() as c, pytest.raises(DBAPIError, match="append-only"):
            c.execute(text(stmt), {"r": rid})


def test_app_role_cannot_rewrite_ledger(app_session):
    for stmt in ("UPDATE trust_ledger SET memo = 'x'", "DELETE FROM trust_ledger"):
        with pytest.raises(Exception, match="permission denied"):
            app_session.execute(text(stmt))
        app_session.rollback()


def test_overdraft_rejected_by_database(owner, seeded, make_resident):
    rid = make_resident()
    owner.add(
        TrustLedger(
            resident_id=rid,
            entry_type="purchase",
            amount_cents=-5,
            balance_after_cents=-5,
            created_at=NOW,
        )
    )
    with pytest.raises(IntegrityError):
        owner.flush()
    assert select(TrustLedger) is not None
