from datetime import timedelta

import pytest
from sqlalchemy import func, select

from isd.engine.authority import AuthorityError, Evidence
from isd.models import AuditLog, OffenseFlag, PointEvent, Sanction, TierHistory
from isd.services import points, sanctions
from isd.services.audit import SYSTEM, verify_chain
from isd.services.entitlement_service import earned_tier, get_entitlements
from tests.conftest import NOW


def _count(s, model):
    return s.execute(select(func.count()).select_from(model)).scalar()


# ---------- points & tiers ----------
def test_course_completion_promotes_and_raises_call_minutes(owner, seeded, make_resident):
    rid = make_resident()
    assert get_entitlements(owner, rid, NOW).features["calls"].limits["minutes_per_day"] == 15
    points.add_point_event(owner, SYSTEM, rid, "basic_course", NOW)
    points.add_point_event(owner, SYSTEM, rid, "basic_course", NOW)  # 100 points -> tier 2
    assert earned_tier(owner, rid, NOW) == 2
    assert get_entitlements(owner, rid, NOW).features["calls"].limits["minutes_per_day"] == 20


def test_commendation_rules(owner, seeded, make_resident, make_staff):
    rid, officer = make_resident(), make_staff("officer")
    with pytest.raises(ValueError):
        points.add_point_event(owner, officer, rid, "staff_commendation", NOW, reason=" ")
    for i in range(3):
        points.add_point_event(owner, officer, rid, "staff_commendation", NOW, reason=f"r{i}")
    with pytest.raises(ValueError, match="limit"):
        points.add_point_event(owner, officer, rid, "staff_commendation", NOW, reason="4th")
    later = NOW + timedelta(days=8)
    points.add_point_event(owner, officer, rid, "staff_commendation", later, reason="new week")


def test_point_event_permissions(owner, seeded, make_resident, make_staff):
    rid, officer = make_resident(), make_staff("officer")
    with pytest.raises(PermissionError):
        points.add_point_event(owner, officer, rid, "basic_course", NOW)  # system-detected
    with pytest.raises(ValueError):
        points.add_point_event(owner, officer, rid, "confirmed_major_infraction", NOW, reason="x")


def test_tier_drops_one_level_per_week(owner, seeded, make_resident):
    rid = make_resident()
    for _ in range(3):
        points.add_point_event(owner, SYSTEM, rid, "program_certificate", NOW)  # 600 -> tier 4
    assert earned_tier(owner, rid, NOW) == 4
    owner.add(PointEvent(resident_id=rid, kind="x", points=-600, source="staff", created_at=NOW))
    owner.flush()
    points.evaluate_tier(owner, rid, NOW)
    assert earned_tier(owner, rid, NOW) == 3
    points.evaluate_tier(owner, rid, NOW + timedelta(days=3))
    assert earned_tier(owner, rid, NOW + timedelta(days=3)) == 3  # still inside the 7 days
    points.evaluate_tier(owner, rid, NOW + timedelta(days=7))
    assert earned_tier(owner, rid, NOW + timedelta(days=7)) == 2
    drops = _count(owner, TierHistory)
    assert drops >= 3


# ---------- sanctions ----------
def test_minor_officer_sanction_locks_features_with_reason_and_keeps_tier_and_baseline(
    owner, seeded, make_resident, make_staff
):
    rid, officer = make_resident(), make_staff("officer")
    points.add_point_event(owner, SYSTEM, rid, "program_certificate", NOW)
    points.add_point_event(owner, SYSTEM, rid, "program_certificate", NOW)  # 400 -> tier 3
    s = sanctions.issue_sanction(owner, officer, rid, "DISRUPT", NOW)
    assert s.status == "active" and s.ends_at == NOW + timedelta(hours=24)
    e = get_entitlements(owner, rid, NOW + timedelta(hours=1))
    reason = e.features["calls"].reasons[0]
    assert (reason.code, reason.ends_at, reason.how_to_appeal) == ("DISRUPT", s.ends_at, "appeal")
    assert e.allowed("commissary") and e.allowed("attorney_calls") and e.allowed("legal_materials")
    assert e.earned_tier == 3  # 375 points still tier 3; sanction itself never touches tier
    assert get_entitlements(owner, rid, s.ends_at).allowed("calls")  # lock ends on its own
    assert verify_chain(owner).ok


def test_weekly_cap_sends_extra_sanctions_to_supervisor(owner, seeded, make_resident, make_staff):
    rid, officer, sup = make_resident(), make_staff("officer"), make_staff("supervisor")
    cap = seeded.officer_weekly_cap
    made = [sanctions.issue_sanction(owner, officer, rid, "CELL_MESS", NOW) for _ in range(cap)]
    assert all(s.status == "active" for s in made)
    over = sanctions.issue_sanction(owner, officer, rid, "CELL_MESS", NOW + timedelta(hours=1))
    assert over.status == "pending"
    assert not get_entitlements(owner, rid, NOW + timedelta(hours=2)).allowed("commissary")
    confirmed = sanctions.confirm_sanction(owner, sup, over.id, NOW + timedelta(hours=3))
    assert confirmed.status == "active"
    # a week later the officer has capacity again
    fresh = sanctions.issue_sanction(owner, officer, rid, "CELL_MESS", NOW + timedelta(days=8))
    assert fresh.status == "active"


def test_significant_sanction_needs_other_supervisor_and_evidence(
    owner, seeded, make_resident, make_staff
):
    rid = make_resident()
    officer, sup1, sup2 = make_staff("officer"), make_staff("supervisor"), make_staff("supervisor")
    colleague = make_staff("officer")
    with pytest.raises(AuthorityError):
        sanctions.issue_sanction(owner, officer, rid, "CAM_BLOCK", NOW)  # no evidence
    ev = Evidence("second_staff_report", reporter_id=colleague.id)
    s = sanctions.issue_sanction(owner, officer, rid, "CAM_BLOCK", NOW, evidence=ev)
    assert s.status == "pending"
    assert get_entitlements(owner, rid, NOW).allowed("calls")  # nothing locked until confirmed
    with pytest.raises(AuthorityError):
        sanctions.confirm_sanction(owner, officer, s.id, NOW)  # officer cannot confirm
    s_sup = sanctions.issue_sanction(owner, sup1, rid, "DEVICE_DAMAGE", NOW, evidence=ev)
    with pytest.raises(AuthorityError) as e:
        sanctions.confirm_sanction(owner, sup1, s_sup.id, NOW)  # supervisor cannot self-confirm
    assert e.value.code == "SAME_PERSON"
    sanctions.confirm_sanction(owner, sup2, s.id, NOW + timedelta(hours=1))
    ent = get_entitlements(owner, rid, NOW + timedelta(hours=2))
    assert not any(ent.allowed(f) for f in ("calls", "commissary", "texting", "chess"))
    assert ent.allowed("attorney_calls") and ent.allowed("basic_education")
    assert all(r.code == "CAM_BLOCK" for r in ent.features["calls"].reasons)


def test_system_event_sanction_flow(owner, seeded, make_resident, make_staff):
    rid, sup = make_resident(), make_staff("supervisor")
    s = sanctions.issue_sanction(
        owner, SYSTEM, rid, "DEVICE_TAMPER", NOW, evidence=Evidence("system_event", ref="evt-9")
    )
    assert s.status == "pending" and s.issued_by is None
    sanctions.confirm_sanction(owner, sup, s.id, NOW)
    assert not get_entitlements(owner, rid, NOW).allowed("video")
    assert get_entitlements(owner, rid, NOW).allowed("calls")


def test_infraction_points_and_reversal_on_overturned_appeal(
    owner, seeded, make_resident, make_staff
):
    rid, officer, sup = make_resident(), make_staff("officer"), make_staff("supervisor")
    s = sanctions.issue_sanction(owner, officer, rid, "DISRUPT", NOW)
    assert points.total_points(owner, rid, NOW) == -25
    appeal = sanctions.file_appeal(owner, s.id, NOW + timedelta(hours=1))
    assert appeal.due_at == NOW + timedelta(hours=1 + seeded.appeal_review_hours)
    with pytest.raises(AuthorityError):
        sanctions.file_appeal(owner, s.id, NOW + timedelta(hours=2))  # duplicate
    with pytest.raises(AuthorityError):
        sanctions.review_appeal(owner, officer, appeal.id, "overturned", "n", NOW)  # not supervisor
    sanctions.review_appeal(owner, sup, appeal.id, "overturned", "insufficient basis", NOW)
    assert owner.get(Sanction, s.id).status == "overturned"
    assert points.total_points(owner, rid, NOW) == 0
    assert get_entitlements(owner, rid, NOW + timedelta(hours=2)).allowed("calls")
    assert verify_chain(owner).ok


def test_appeal_reviewer_cannot_be_issuer(owner, seeded, make_resident, make_staff):
    rid, sup = make_resident(), make_staff("supervisor")
    colleague = make_staff("officer")
    ev = Evidence("second_staff_report", reporter_id=colleague.id)
    s = sanctions.issue_sanction(owner, sup, rid, "DEVICE_DAMAGE", NOW, evidence=ev)
    other = make_staff("supervisor")
    sanctions.confirm_sanction(owner, other, s.id, NOW)
    appeal = sanctions.file_appeal(owner, s.id, NOW)
    with pytest.raises(AuthorityError) as e:
        sanctions.review_appeal(owner, sup, appeal.id, "upheld", "n", NOW)
    assert e.value.code == "SAME_PERSON"
    sanctions.review_appeal(owner, other, appeal.id, "upheld", "ok", NOW)
    assert sanctions.overdue_appeals(owner, NOW + timedelta(days=30)) == []


def test_db_rejects_self_confirmation(owner, seeded, make_resident, make_staff):
    from sqlalchemy.exc import IntegrityError

    rid, sup = make_resident(), make_staff("supervisor")
    s = Sanction(
        resident_id=rid,
        infraction_code="X",
        scope="video",
        reason_code="X",
        issued_by=sup.id,
        confirmed_by=sup.id,
    )
    owner.add(s)
    with pytest.raises(IntegrityError):
        owner.flush()


# ---------- entitlements ----------
def test_get_entitlements_is_read_only(owner, seeded, make_resident):
    rid = make_resident(prior_returns=3)
    owner.flush()
    owner.add(OffenseFlag(resident_id=rid, offense_category="SEX_OFFENSE", added_at=NOW))
    owner.flush()
    before = (_count(owner, AuditLog), _count(owner, TierHistory), _count(owner, PointEvent))
    e = get_entitlements(owner, rid, NOW)
    assert not owner.new and not owner.dirty
    after = (_count(owner, AuditLog), _count(owner, TierHistory), _count(owner, PointEvent))
    assert before == after
    assert e.ceiling_tier == 9
    assert e.features["video"].reasons[0].code in ("OFFENSE_RESTRICTION", "TIER_LOCKED")


def test_offense_restriction_shown_with_reason_text(owner, seeded, make_resident):
    rid = make_resident()
    owner.add(OffenseFlag(resident_id=rid, offense_category="VIOLENCE", added_at=NOW))
    owner.flush()
    for _ in range(3):
        points.add_point_event(owner, SYSTEM, rid, "program_certificate", NOW)
    e = get_entitlements(owner, rid, NOW)
    r = [r for r in e.features["texting"].reasons if r.code == "OFFENSE_RESTRICTION"][0]
    assert "Texting is restricted" in r.detail and r.how_to_appeal == "appeal"


def test_blocked_contacts_returned_at_any_tier(owner, seeded, make_resident):
    from isd.models import Contact

    rid = make_resident()
    c = Contact(resident_id=rid, name="Synthetic Contact", type="family", blocked=True)
    owner.add(c)
    owner.flush()
    assert get_entitlements(owner, rid, NOW).blocked_contact_ids == (c.id,)


def test_only_the_entitlement_service_uses_the_composer():
    """Invariant 2: feature code must go through get_entitlements."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "isd"
    allowed = {"engine/entitlements.py", "services/entitlement_service.py"}
    offenders = [
        str(p.relative_to(root))
        for p in root.rglob("*.py")
        if "compute_entitlements" in p.read_text() and str(p.relative_to(root)) not in allowed
    ]
    assert offenders == []
