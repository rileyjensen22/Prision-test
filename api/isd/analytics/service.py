"""Outcomes dashboard, outcome entry and the researcher export (evaluation only, invariant 17).

Read-mostly and one-way: this package reads what the system recorded and nothing in the system
reads from it. There are no per-person scores; every number is a cohort aggregate, small groups are
suppressed, and the export carries pseudonyms and bands instead of identifiers or dates.
"""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from isd.analytics.rules import (
    assert_no_identifiers,
    band,
    cohort_label,
    cohort_labels_for_export,
    summarize_cohort,
)
from isd.engine.public_log import pseudonym, suppress
from isd.models import (
    CallRecord,
    Certificate,
    CourseProgress,
    Message,
    OutcomeRecord,
    Resident,
    Sanction,
    TierHistory,
)
from isd.services.audit import Actor, append_audit
from isd.services.config_store import get_current

WINDOWS = (6, 12, 24)
OUTCOMES = ("no_return", "returned", "unknown")


class OutcomeError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _minimum(session: Session) -> int:
    return int(get_current(session, "compliance").payload["outcomes_min_cell"])


def _by_resident(session: Session, stmt) -> dict[int, int]:
    return {rid: n for rid, n in session.execute(stmt)}


def _tier_bounds(session: Session) -> tuple[dict[int, int], dict[int, int]]:
    start: dict[int, int] = {}
    now_tier: dict[int, int] = {}
    rows = session.execute(
        select(TierHistory.resident_id, TierHistory.from_tier, TierHistory.to_tier).order_by(
            TierHistory.id
        )
    )
    for rid, frm, to in rows:
        start.setdefault(rid, frm)
        now_tier[rid] = to
    return start, now_tier


def latest_outcomes(session: Session) -> dict[tuple[int, int], str]:
    """The newest record for each resident and window wins (a fix is a newer row)."""
    out: dict[tuple[int, int], str] = {}
    rows = session.execute(
        select(
            OutcomeRecord.resident_id, OutcomeRecord.window_months, OutcomeRecord.outcome
        ).order_by(OutcomeRecord.id)
    )
    for rid, window, outcome in rows:
        out[(rid, window)] = outcome
    return out


def _rows(session: Session, now: datetime) -> list[dict]:
    """One working row per resident. It stays in this module; outputs reduce it."""
    residents = session.execute(select(Resident).order_by(Resident.id)).scalars().all()
    start, current = _tier_bounds(session)
    courses = _by_resident(
        session,
        select(CourseProgress.resident_id, func.count())
        .where(CourseProgress.completed_at.is_not(None))
        .group_by(CourseProgress.resident_id),
    )
    certs = _by_resident(
        session,
        select(Certificate.resident_id, func.count()).group_by(Certificate.resident_id),
    )
    calls = _by_resident(
        session, select(CallRecord.resident_id, func.count()).group_by(CallRecord.resident_id)
    )
    texts = _by_resident(
        session,
        select(Message.resident_id, func.count())
        .where(Message.direction == "out")
        .group_by(Message.resident_id),
    )
    sanctions = _by_resident(
        session,
        select(Sanction.resident_id, func.count())
        .where(Sanction.status.in_(("active", "expired")))
        .group_by(Sanction.resident_id),
    )
    rows = []
    for r in residents:
        weeks = max(1.0, (now - r.created_at).total_seconds() / (7 * 86400))
        rows.append(
            {
                "resident_id": r.id,
                "code": r.code,
                "name": r.display_name,
                "created_at": r.created_at,
                "cohort": cohort_label(r.created_at),
                "tier_start": start.get(r.id, 1),
                "tier_now": current.get(r.id, 1),
                "courses": courses.get(r.id, 0),
                "certificates": certs.get(r.id, 0),
                "contacts": calls.get(r.id, 0) + texts.get(r.id, 0),
                "sanctions": sanctions.get(r.id, 0),
                "weeks": weeks,
            }
        )
    return rows


def dashboard(session: Session, now: datetime) -> dict:
    minimum = _minimum(session)
    rows = _rows(session, now)
    outcomes = latest_outcomes(session)
    by_cohort: dict[str, list[dict]] = {}
    for row in rows:
        by_cohort.setdefault(row["cohort"], []).append(row)
    cohorts = []
    for label in sorted(by_cohort):
        group = by_cohort[label]
        entry = summarize_cohort(label, group, minimum)
        if len(group) >= minimum:
            entry["outcomes"] = {
                str(w): _outcome_tally(group, outcomes, w, minimum) for w in WINDOWS
            }
        cohorts.append(entry)
    return {
        "generated_at": now.isoformat(),
        "minimum_group_size": minimum,
        "cohorts": cohorts,
        "note": "Evaluation only; never used for tiers, sanctions or restrictions.",
    }


def _outcome_tally(group: list[dict], outcomes: dict, window: int, minimum: int) -> dict:
    tally = {"no_return": 0, "returned": 0, "unknown": 0, "not_entered": 0}
    for row in group:
        tally[outcomes.get((row["resident_id"], window), "not_entered")] += 1
    return {key: suppress(n, minimum) for key, n in tally.items()}


def record_outcome(
    session: Session,
    actor: Actor,
    resident_code: str,
    window: int,
    outcome: str,
    source: str,
    now: datetime,
) -> OutcomeRecord:
    if window not in WINDOWS:
        raise OutcomeError("BAD_WINDOW", "window must be 6, 12 or 24 months")
    if outcome not in OUTCOMES:
        raise OutcomeError("BAD_OUTCOME", f"outcome must be one of {', '.join(OUTCOMES)}")
    if len(source.strip()) < 3:
        raise OutcomeError("SOURCE_REQUIRED", "say which customer record this came from")
    resident = session.execute(select(Resident).where(Resident.code == resident_code)).scalar()
    if resident is None:
        raise OutcomeError("NOT_FOUND", "resident not found")
    previous = session.execute(
        select(OutcomeRecord)
        .where(OutcomeRecord.resident_id == resident.id, OutcomeRecord.window_months == window)
        .order_by(OutcomeRecord.id.desc())
        .limit(1)
    ).scalar()
    row = OutcomeRecord(
        resident_id=resident.id,
        window_months=window,
        outcome=outcome,
        source=source.strip()[:80],
        corrects_id=previous.id if previous else None,
        entered_by=actor.id,
        entered_at=now,
    )
    session.add(row)
    session.flush()
    append_audit(
        session,
        actor,
        "outcome_recorded",
        "resident",
        resident.code,
        reason_code="OUTCOME_ENTRY",
        payload={"window_months": window, "corrects": previous.id if previous else None},
    )
    return row


def export(session: Session, actor: Actor, reason: str, salt: str, now: datetime) -> dict:
    """Pseudonymized researcher rows. Off unless enabled; every export is audited."""
    compliance = get_current(session, "compliance").payload
    if not compliance.get("researcher_export_enabled"):
        raise OutcomeError("EXPORT_DISABLED", "the researcher export is turned off")
    if len(reason.strip()) < 3:
        raise OutcomeError("REASON_REQUIRED", "a stated reason is required")
    minimum = int(compliance["outcomes_min_cell"])
    rows = _rows(session, now)
    outcomes = latest_outcomes(session)
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["cohort"]] = counts.get(r["cohort"], 0) + 1
    labels = cohort_labels_for_export(counts, minimum)
    records = [
        {
            "pseudonym": pseudonym("S", r["code"], salt),
            "cohort": labels[r["cohort"]],
            "weeks_on_unit": band(int(r["weeks"]), (4, 13, 26, 52)),
            "tier_start": r["tier_start"],
            "tier_now": r["tier_now"],
            "courses_completed": band(r["courses"], (1, 3, 6)),
            "certificates": band(r["certificates"], (1, 3, 6)),
            "contacts_per_week": band(int(r["contacts"] / r["weeks"]), (1, 5, 15)),
            "sanctions": band(r["sanctions"], (1, 3, 6)),
            **{
                f"outcome_{w}m": outcomes.get((r["resident_id"], w), "not_entered") for w in WINDOWS
            },
        }
        for r in rows
    ]
    forbidden = [x for r in rows for x in (r["code"], r["name"])]
    assert_no_identifiers(records, forbidden)
    append_audit(
        session,
        actor,
        "researcher_export",
        "export",
        "outcomes",
        reason_code="RESEARCH_EXPORT",
        payload={"rows": len(records), "reason": reason.strip()},
    )
    return {"generated_at": now.isoformat(), "rows": records}
