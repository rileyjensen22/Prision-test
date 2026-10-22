"""Outcomes dashboard and researcher export: pseudonymized, suppressed, audited, and one-way."""

import re
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from isd.analytics import service
from isd.analytics.service import OutcomeError
from isd.models import AuditLog, CourseProgress, OutcomeRecord, Resident, Sanction
from isd.services.audit import SYSTEM
from isd.services.config_store import get_current, set_config
from tests.conftest import NOW

SALT = "unit-test-research-salt"


@pytest.fixture
def cohort(owner, seeded):
    """Seven residents admitted in one quarter, with a spread of activity."""
    ids = []
    for i in range(7):
        r = Resident(
            code=f"OUT-{i}",
            display_name=f"Synthetic Person {i}",
            created_at=NOW - timedelta(weeks=8),
        )
        owner.add(r)
        owner.flush()
        ids.append(r.id)
        if i < 3:
            owner.add(
                CourseProgress(
                    resident_id=r.id, course_code="NUM101", lessons_done=[], completed_at=NOW
                )
            )
    owner.add(
        Sanction(
            resident_id=ids[0],
            infraction_code="DISRUPT",
            scope="communication",
            reason_code="DISRUPT",
            status="active",
        )
    )
    owner.flush()
    return ids


def enable_export(owner):
    payload = dict(get_current(owner, "compliance").payload, researcher_export_enabled=True)
    set_config(owner, SYSTEM, "compliance", payload, "test")


def test_dashboard_has_cohort_aggregates_and_no_individuals(owner, cohort):
    out = service.dashboard(owner, NOW)
    row = next(c for c in out["cohorts"] if c["residents"] == 7)
    assert row["share_completed_a_course"] == round(3 / 7, 2)
    assert row["sanctions_per_100_weeks"] is not None
    text_dump = repr(out)
    assert "OUT-0" not in text_dump and "Synthetic Person" not in text_dump
    assert set(row["outcomes"]) == {"6", "12", "24"}


def test_small_cohorts_are_suppressed_on_the_dashboard(owner, seeded, make_resident):
    make_resident()
    out = service.dashboard(owner, NOW)
    assert all(c["residents"] == "<5" for c in out["cohorts"] if "share_promoted" not in c)
    assert not any("outcomes" in c for c in out["cohorts"] if c["residents"] == "<5")


def test_outcomes_are_append_only_and_a_fix_is_a_new_row(owner, cohort, make_staff):
    admin = make_staff("admin")
    first = service.record_outcome(
        owner, admin, "OUT-1", 12, "returned", "state record #synthetic", NOW
    )
    fix = service.record_outcome(owner, admin, "OUT-1", 12, "no_return", "corrected record", NOW)
    assert fix.corrects_id == first.id
    assert service.latest_outcomes(owner)[(cohort[1], 12)] == "no_return"
    for sql in ("UPDATE outcome_records SET outcome = 'unknown'", "DELETE FROM outcome_records"):
        with pytest.raises(DBAPIError):
            with owner.begin_nested():
                owner.execute(text(sql))
    assert (
        owner.execute(select(AuditLog).where(AuditLog.action == "outcome_recorded")).scalars().all()
    )


@pytest.mark.parametrize(
    ("window", "outcome", "source", "who", "code"),
    [
        (7, "returned", "state record", "OUT-1", "BAD_WINDOW"),
        (6, "maybe", "state record", "OUT-1", "BAD_OUTCOME"),
        (6, "returned", " ", "OUT-1", "SOURCE_REQUIRED"),
        (6, "returned", "state record", "NOBODY", "NOT_FOUND"),
    ],
)
def test_bad_outcome_entries_are_refused(
    owner, cohort, make_staff, window, outcome, source, who, code
):
    with pytest.raises(OutcomeError) as e:
        service.record_outcome(owner, make_staff("admin"), who, window, outcome, source, NOW)
    assert e.value.code == code
    assert owner.execute(select(OutcomeRecord)).first() is None


def test_export_is_off_by_default_and_needs_a_reason(owner, cohort, make_staff):
    admin = make_staff("admin")
    with pytest.raises(OutcomeError) as e:
        service.export(owner, admin, "study", SALT, NOW)
    assert e.value.code == "EXPORT_DISABLED"
    enable_export(owner)
    with pytest.raises(OutcomeError) as e:
        service.export(owner, admin, " ", SALT, NOW)
    assert e.value.code == "REASON_REQUIRED"


def test_export_has_no_direct_identifiers(owner, cohort, make_staff):
    enable_export(owner)
    service.record_outcome(owner, make_staff("admin"), "OUT-2", 6, "no_return", "state record", NOW)
    data = service.export(owner, make_staff("auditor"), "evaluation study", SALT, NOW)
    rows = data["rows"]
    assert len(rows) >= 7
    blob = repr(data)
    for r in owner.execute(select(Resident)).scalars():
        assert r.code not in blob and r.display_name not in blob
    assert not re.search(r"\d{4}-\d{2}-\d{2}", blob.replace(data["generated_at"], ""))  # no dates
    assert {"resident_code", "display_name", "cell", "device", "id"}.isdisjoint(rows[0])
    mine = next(r for r in rows if r["outcome_6m"] == "no_return")
    assert mine["pseudonym"].startswith("S-")
    assert (
        owner.execute(select(AuditLog).where(AuditLog.action == "researcher_export"))
        .scalar()
        .payload["reason"]
        == "evaluation study"
    )


def test_pseudonyms_are_stable_per_salt_and_differ_across_salts(owner, cohort, make_staff):
    enable_export(owner)
    a = service.export(owner, make_staff("admin"), "study", SALT, NOW)["rows"]
    b = service.export(owner, make_staff("admin"), "study", SALT, NOW)["rows"]
    c = service.export(owner, make_staff("admin"), "study", "another-salt-value", NOW)["rows"]
    assert [r["pseudonym"] for r in a] == [r["pseudonym"] for r in b]
    assert {r["pseudonym"] for r in a}.isdisjoint(r["pseudonym"] for r in c)


def test_export_does_not_reuse_the_public_log_pseudonyms(owner, cohort, make_staff):
    from isd.engine.public_log import pseudonym

    enable_export(owner)
    rows = service.export(owner, make_staff("admin"), "study", SALT, NOW)["rows"]
    public = pseudonym("R", "OUT-0", SALT)
    assert public not in {r["pseudonym"] for r in rows}


def test_small_cohorts_are_merged_in_the_export(owner, seeded, cohort, make_staff):
    enable_export(owner)
    lone = Resident(code="LONE-1", display_name="Synthetic", created_at=NOW - timedelta(days=400))
    owner.add(lone)
    owner.flush()
    rows = service.export(owner, make_staff("admin"), "study", SALT, NOW)["rows"]
    from isd.engine.public_log import pseudonym

    mine = next(r for r in rows if r["pseudonym"] == pseudonym("S", "LONE-1", SALT))
    assert mine["cohort"] == "OTHER"  # a cohort of one is not shown as its own group
    assert any(r["cohort"] != "OTHER" for r in rows)  # the seven-person cohort still is


# ---------------- over HTTP ----------------
@pytest.mark.usefixtures("committed_config")
def test_outcomes_api_roles(client, staff_tokens):
    for role, expected in (("officer", 403), ("supervisor", 200), ("admin", 200), ("auditor", 200)):
        assert client.get("/staff/outcomes", headers=staff_tokens[role]).status_code == expected
    body = {
        "resident_code": "NOBODY",
        "window_months": 6,
        "outcome": "returned",
        "source": "state record",
    }
    assert (
        client.post("/staff/outcomes", json=body, headers=staff_tokens["supervisor"]).status_code
        == 403
    )
    assert (
        client.post("/staff/outcomes", json=body, headers=staff_tokens["admin"]).status_code == 404
    )
    assert (
        client.get(
            "/staff/outcomes/export?reason=study", headers=staff_tokens["supervisor"]
        ).status_code
        == 403
    )
    off = client.get("/staff/outcomes/export?reason=study", headers=staff_tokens["admin"])
    assert off.status_code == 403 and off.json()["detail"]["code"] == "EXPORT_DISABLED"


# ---------------- invariant 17: nothing decides from analytics ----------------
API = Path(__file__).resolve().parents[1] / "isd"
ALLOWED_READERS = {
    "routers/staff_outcomes.py",
    "analytics/service.py",
    "analytics/rules.py",
    "simulation.py",
}


def test_only_the_outcomes_router_imports_analytics():
    pattern = re.compile(
        r"^\s*(from|import)\s+isd\.analytics|^\s*from\s+isd\s+import\s+.*\banalytics\b", re.M
    )
    offenders = [
        str(p.relative_to(API))
        for p in API.rglob("*.py")
        if str(p.relative_to(API)) not in ALLOWED_READERS and pattern.search(p.read_text())
    ]
    assert offenders == []


def test_the_engine_and_decision_services_never_touch_outcome_data():
    decision_code = [*API.glob("engine/*.py")] + [
        API / "services" / f"{n}.py"
        for n in ("entitlement_service", "points", "sanctions", "daily", "welfare")
    ]
    for path in decision_code:
        src = path.read_text()
        assert (
            "analytics" not in src and "OutcomeRecord" not in src and "outcome_records" not in src
        ), path.name


def test_outcome_table_is_referenced_only_by_analytics_and_its_own_definition():
    allowed = {"models.py", "analytics/service.py"}
    offenders = [
        str(p.relative_to(API))
        for p in API.rglob("*.py")
        if str(p.relative_to(API)) not in allowed and "OutcomeRecord" in p.read_text()
    ]
    assert offenders == []


def test_no_risk_score_columns_exist(owner):
    cols = owner.execute(
        text(
            "SELECT table_name, column_name FROM information_schema.columns"
            " WHERE table_schema = 'public'"
        )
    ).all()
    assert [c for c in cols if re.search(r"risk|recidiv|predict", c[1], re.I)] == []
