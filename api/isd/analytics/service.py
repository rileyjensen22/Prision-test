"""Outcomes dashboard, outcome entry and the researcher export (evaluation only, invariant 17).

Read-mostly and one-way: this package reads what the system recorded and nothing in the system
reads from it. There are no per-person scores; every number is a cohort aggregate, small groups are
suppressed, and the export carries pseudonyms and bands instead of identifiers or dates.
"""

import csv
import io
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
    OutcomeImportBatch,
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


# ---------------- CSV import ----------------
MAX_IMPORT_ROWS = 5000
IMPORT_COLUMNS = ("resident_code", "window_months", "outcome")


def _latest_outcomes(session: Session, ids: list[int]) -> dict[tuple[int, int], OutcomeRecord]:
    rows = session.execute(
        select(OutcomeRecord)
        .where(OutcomeRecord.resident_id.in_(ids))
        .order_by(OutcomeRecord.id)  # later rows replace earlier ones below
    ).scalars()
    return {(r.resident_id, r.window_months): r for r in rows}


def _parse_import(text: str) -> tuple[list[dict], list[dict]]:
    """(rows with their line numbers, problems). Nothing here touches the database."""
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    if not reader.fieldnames or set(IMPORT_COLUMNS) - {f.strip() for f in reader.fieldnames}:
        raise OutcomeError("BAD_FILE", f"the first row must name the columns {IMPORT_COLUMNS}")
    rows, problems = [], []
    for line, raw in enumerate(reader, start=2):
        if len(rows) + len(problems) >= MAX_IMPORT_ROWS:
            raise OutcomeError("TOO_MANY_ROWS", f"at most {MAX_IMPORT_ROWS} rows per file")
        row = {k.strip(): (v or "").strip() for k, v in raw.items() if k}
        try:
            row["window_months"] = int(row["window_months"])
        except ValueError:
            problems.append({"line": line, "code": "BAD_WINDOW", "message": "window_months"})
            continue
        if row["window_months"] not in WINDOWS:
            problems.append({"line": line, "code": "BAD_WINDOW", "message": "6, 12 or 24"})
        elif row["outcome"] not in OUTCOMES:
            problems.append({"line": line, "code": "BAD_OUTCOME", "message": row["outcome"][:20]})
        else:
            rows.append({**row, "line": line})
    return rows, problems


def import_outcomes(
    session: Session,
    actor: Actor,
    text: str,
    source: str,
    label: str,
    now: datetime,
    *,
    dry_run: bool = True,
) -> dict:
    """Adds outcomes from a CSV (resident_code, window_months, outcome). All or nothing: any bad
    row means nothing is written. A row that repeats the current answer is skipped, a row that
    differs is added as a correcting entry pointing at the one it replaces (append-only). A dry
    run reports exactly what an import would do and writes nothing, not even an audit entry."""
    if len(source.strip()) < 3:
        raise OutcomeError("SOURCE_REQUIRED", "say which customer record this came from")
    rows, problems = _parse_import(text)
    codes = {r["resident_code"] for r in rows}
    residents = {
        r.code: r
        for r in session.execute(select(Resident).where(Resident.code.in_(codes))).scalars()
    }
    for r in rows:
        if r["resident_code"] not in residents:
            problems.append({"line": r["line"], "code": "NOT_FOUND", "message": "resident code"})
    latest = _latest_outcomes(session, [r.id for r in residents.values()])
    plan = []
    for r in rows:
        res = residents.get(r["resident_code"])
        if res is None:
            continue
        current = latest.get((res.id, r["window_months"]))
        action = (
            "new"
            if current is None
            else "unchanged"
            if current.outcome == r["outcome"]
            else "correction"
        )
        plan.append(
            {**r, "action": action, "resident_id": res.id, "corrects_id": current and current.id}
        )
        latest[(res.id, r["window_months"])] = (
            OutcomeRecord(  # later lines in the file see this one
                id=0, resident_id=res.id, window_months=r["window_months"], outcome=r["outcome"]
            )
            if action != "unchanged"
            else current
        )
    counts = {
        a: sum(1 for p in plan if p["action"] == a) for a in ("new", "correction", "unchanged")
    }
    result = {
        "dry_run": dry_run,
        "rows": len(rows) + len(problems),
        "counts": counts,
        "problems": sorted(problems, key=lambda p: p["line"]),
        "preview": [
            {k: p[k] for k in ("line", "resident_code", "window_months", "outcome", "action")}
            for p in plan[:50]
        ],
        "imported": False,
    }
    if dry_run or problems:
        return result
    batch = OutcomeImportBatch(
        label=label.strip()[:80] or "import",
        source=source.strip()[:80],
        rows_total=len(plan),
        rows_new=counts["new"],
        rows_correcting=counts["correction"],
        rows_unchanged=counts["unchanged"],
        entered_by=actor.id,
        entered_at=now,
    )
    session.add(batch)
    session.flush()
    chain: dict[tuple[int, int], int] = {}  # a second line for the same person points at the first
    for p in plan:
        if p["action"] == "unchanged":
            continue
        key = (p["resident_id"], p["window_months"])
        row = OutcomeRecord(
            resident_id=p["resident_id"],
            window_months=p["window_months"],
            outcome=p["outcome"],
            source=source.strip()[:80],
            corrects_id=chain.get(key, p["corrects_id"]),
            entered_by=actor.id,
            entered_at=now,
            batch_id=batch.id,
        )
        session.add(row)
        session.flush()
        chain[key] = row.id
    append_audit(
        session,
        actor,
        "outcomes_imported",
        "outcome_import_batch",
        str(batch.id),
        reason_code="OUTCOME_IMPORT",
        payload={**counts, "source": batch.source},
    )
    return {**result, "imported": True, "batch_id": batch.id}
