import pytest
from hypothesis import given
from hypothesis import strategies as st

from isd.engine.authority import (
    AuthorityError,
    Evidence,
    check_appeal_review,
    check_confirm,
    decide_issue,
    needs_supervisor,
)

SYS_EV = Evidence("system_event", ref="evt-1")


def test_minor_officer_immediate_applies_until_cap(cfg):
    rule = cfg.infractions["DISRUPT"]
    assert decide_issue(rule, "officer", 1, None, 0, cfg).status == "active"
    assert (
        decide_issue(rule, "officer", 1, None, cfg.officer_weekly_cap - 1, cfg).status == "active"
    )
    over = decide_issue(rule, "officer", 1, None, cfg.officer_weekly_cap, cfg)
    assert over.status == "pending" and not over.applied_immediately


@pytest.mark.parametrize(
    "code", ["STAFF_DISRESPECT", "CAM_BLOCK", "DEVICE_DAMAGE", "DEVICE_TAMPER"]
)
def test_larger_or_subjective_needs_supervisor_and_evidence(cfg, code):
    rule = cfg.infractions[code]
    assert needs_supervisor(rule)
    with pytest.raises(AuthorityError):
        decide_issue(rule, "officer", 1, None, 0, cfg)
    ev = SYS_EV if code == "DEVICE_TAMPER" else Evidence("second_staff_report", reporter_id=2)
    assert decide_issue(rule, "officer", 1, ev, 0, cfg).status == "pending"


def test_second_report_must_be_a_different_person(cfg):
    rule = cfg.infractions["CAM_BLOCK"]
    with pytest.raises(AuthorityError):
        decide_issue(rule, "officer", 1, Evidence("second_staff_report", reporter_id=1), 0, cfg)


def test_device_tamper_requires_system_event(cfg):
    rule = cfg.infractions["DEVICE_TAMPER"]
    with pytest.raises(AuthorityError):
        decide_issue(rule, "officer", 1, Evidence("second_staff_report", reporter_id=2), 0, cfg)


def test_non_issuer_roles_rejected(cfg):
    for role in ("admin", "auditor"):
        with pytest.raises(AuthorityError):
            decide_issue(cfg.infractions["DISRUPT"], role, 1, None, 0, cfg)


@given(
    st.sampled_from(
        ["DISRUPT", "CELL_MESS", "STAFF_DISRESPECT", "CAM_BLOCK", "DEVICE_TAMPER", "DEVICE_DAMAGE"]
    ),
    st.integers(0, 10),
    st.sampled_from(["officer", "supervisor"]),
)
def test_no_significant_sanction_is_ever_active_without_confirmation(cfg, code, count, role):
    rule = cfg.infractions[code]
    ev = SYS_EV
    d = decide_issue(rule, role, 1, ev, count, cfg)
    if needs_supervisor(rule):
        assert d.status == "pending" and not d.applied_immediately


@given(st.integers(1, 50), st.integers(1, 50))
def test_issuer_and_confirmer_must_differ(issuer, confirmer):
    if issuer == confirmer:
        with pytest.raises(AuthorityError) as e:
            check_confirm("pending", issuer, "supervisor", confirmer)
        assert e.value.code == "SAME_PERSON"
    else:
        check_confirm("pending", issuer, "supervisor", confirmer)


def test_confirm_requires_supervisor_and_pending():
    with pytest.raises(AuthorityError):
        check_confirm("pending", 1, "officer", 2)
    with pytest.raises(AuthorityError):
        check_confirm("active", 1, "supervisor", 2)
    check_confirm("pending", None, "supervisor", 2)  # system-issued


def test_appeal_reviewer_not_issuer():
    with pytest.raises(AuthorityError):
        check_appeal_review(3, "supervisor", 3)
    with pytest.raises(AuthorityError):
        check_appeal_review(3, "officer", 4)
    check_appeal_review(3, "supervisor", 4)
