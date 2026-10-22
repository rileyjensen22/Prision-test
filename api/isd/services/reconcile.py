"""Nightly reconciliation (invariant 15): do balances match their append-only ledgers?

Checks the trust ledger and the work-earnings ledger against each other and against the orders
and task submissions they came from. Every run is recorded (append-only). Any mismatch is also
written to the audit log as `reconciliation_mismatch`, which is the alert staff see on the
dashboard. The check reads only; it never changes a balance. A real mismatch is for people to
investigate and correct with a new entry.
"""

from datetime import datetime

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from isd.models import ReconciliationRun
from isd.services.audit import SYSTEM, Actor, append_audit

MAX_PROBLEMS = 50

# Each query returns the offending rows (resident id, a ledger id). No rows means the check holds.
CHECKS: dict[str, str] = {
    "trust balance is the running total of its entries": """
        SELECT resident_id, id AS ref FROM (
          SELECT id, resident_id, balance_after_cents,
                 SUM(amount_cents) OVER (PARTITION BY resident_id ORDER BY id) AS running
          FROM trust_ledger) t
        WHERE running <> balance_after_cents""",
    "no trust balance is negative": """
        SELECT resident_id, id AS ref FROM trust_ledger WHERE balance_after_cents < 0""",
    "each purchase equals its order total": """
        SELECT l.resident_id, l.id AS ref FROM trust_ledger l
        JOIN commissary_orders o ON o.id = l.order_id
        WHERE l.entry_type = 'purchase' AND -l.amount_cents <> o.total_cents""",
    "earned pay was split without losing a cent": """
        SELECT resident_id, id AS ref FROM earnings_ledger
        WHERE entry_type = 'earned'
          AND gross_cents <> resident_cents + facility_cents + deductions_cents""",
    "each accepted task has one earning for its pay, and nothing else does": """
        SELECT s.resident_id, s.id AS ref FROM task_submissions s
        LEFT JOIN earnings_ledger e ON e.submission_id = s.id
        WHERE (s.accepted AND s.pay_cents > 0 AND (e.id IS NULL OR e.gross_cents <> s.pay_cents))
           OR (NOT s.accepted AND e.id IS NOT NULL)
        UNION ALL
        SELECT e.resident_id, e.id FROM earnings_ledger e
        LEFT JOIN task_submissions s ON s.id = e.submission_id
        WHERE e.entry_type = 'earned' AND s.id IS NULL""",
    "no one has been paid out more than they earned": """
        SELECT resident_id, MIN(id) AS ref FROM earnings_ledger
        GROUP BY resident_id HAVING SUM(resident_cents) < 0""",
    "each payout matches one trust-account entry, and each work deposit has a payout": """
        SELECT e.resident_id, e.id AS ref FROM earnings_ledger e
        LEFT JOIN trust_ledger t ON t.id = e.trust_ledger_id
        WHERE e.entry_type = 'payout'
          AND (t.id IS NULL OR t.entry_type <> 'job_payout'
               OR t.amount_cents <> -e.resident_cents OR t.resident_id <> e.resident_id)
        UNION ALL
        SELECT t.resident_id, t.id FROM trust_ledger t
        LEFT JOIN earnings_ledger e ON e.trust_ledger_id = t.id
        WHERE t.entry_type = 'job_payout' AND e.id IS NULL""",
}


def run_checks(session: Session) -> tuple[dict, list[dict]]:
    checked = {
        "trust_entries": session.execute(text("SELECT count(*) FROM trust_ledger")).scalar(),
        "earnings_entries": session.execute(text("SELECT count(*) FROM earnings_ledger")).scalar(),
        "checks": len(CHECKS),
    }
    problems: list[dict] = []
    for name, sql in CHECKS.items():
        for row in session.execute(text(sql + f" LIMIT {MAX_PROBLEMS}")):
            problems.append({"check": name, "resident_id": row.resident_id, "ref": row.ref})
    return checked, problems[:MAX_PROBLEMS]


def reconcile(session: Session, now: datetime, actor: Actor = SYSTEM) -> dict:
    checked, problems = run_checks(session)
    run = ReconciliationRun(at=now, ok=not problems, checked=checked, problems=problems)
    session.add(run)
    session.flush()
    if problems:
        append_audit(
            session,
            actor,
            "reconciliation_mismatch",
            "reconciliation_run",
            run.id,
            "RECONCILIATION",
            payload={"problems": len(problems), "checks": sorted({p["check"] for p in problems})},
        )
    return {"run_id": run.id, "ok": run.ok, "checked": checked, "problems": problems}


def latest_runs(session: Session, limit: int = 14) -> list[dict]:
    return [
        {
            "id": r.id,
            "at": r.at.isoformat(),
            "ok": r.ok,
            "checked": r.checked,
            "problems": r.problems,
        }
        for r in session.execute(
            select(ReconciliationRun).order_by(ReconciliationRun.id.desc()).limit(limit)
        ).scalars()
    ]


def runs_count(session: Session) -> int:
    return session.execute(select(func.count()).select_from(ReconciliationRun)).scalar()
