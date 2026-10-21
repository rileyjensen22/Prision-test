"""Public log export rules (CLAUDE.md section 10). Pure: shapes records and removes identity.

The export may show reason codes, durations and outcomes. It must never show a name, an
internal id, a staff member, a cell, free text, or evidence. Every record is built from an
explicit allow-list of fields, and `assert_clean` re-checks it before it is written.
"""

import hashlib
import hmac
from collections import Counter
from datetime import date, datetime, timedelta

RECORD_FIELDS = (
    "event",  # pseudonymous id of the sanction
    "resident",  # pseudonymous resident id
    "week",  # Monday of the week it was issued (not the exact day)
    "code",
    "severity",
    "duration_hours",
    "hours_served",
    "issued_by_role",
    "confirmed_by_role",
    "outcome",
    "appeal",
)
OUTCOMES = ("pending", "active", "ended", "rejected", "overturned")
APPEALS = ("none", "open", "upheld", "overturned")


def pseudonym(prefix: str, value: str, salt: str) -> str:
    """Stable, non-reversible id. Without the salt it cannot be linked back to a person."""
    digest = hmac.new(salt.encode(), f"{prefix}:{value}".encode(), hashlib.sha256).hexdigest()
    return f"{prefix}-{digest[:12]}"


def week_start(when: date | datetime) -> str:
    d = when.date() if isinstance(when, datetime) else when
    return (d - timedelta(days=d.weekday())).isoformat()


def suppress(count: int, minimum: int) -> int | str:
    """Small counts can identify people, so show them as '<k' instead of the number."""
    return f"<{minimum}" if 0 < count < minimum else count


def outcome_of(status: str, ends_at: datetime | None, now: datetime) -> str:
    if status == "active":
        return "ended" if ends_at and ends_at <= now else "active"
    return status


def assert_clean(record: dict) -> dict:
    extra = set(record) - set(RECORD_FIELDS)
    if extra:
        raise ValueError(f"public record has non-public fields: {sorted(extra)}")
    if record["outcome"] not in OUTCOMES or record["appeal"] not in APPEALS:
        raise ValueError("unexpected outcome or appeal value")
    return record


def build_record(
    *,
    sanction_id: int,
    resident_code: str,
    issued_at: datetime,
    code: str,
    severity: str,
    duration_hours: int,
    hours_served: float,
    issued_by_role: str,
    confirmed_by_role: str | None,
    status: str,
    ends_at: datetime | None,
    appeal: str,
    now: datetime,
    salt: str,
) -> dict:
    return assert_clean(
        {
            "event": pseudonym("E", str(sanction_id), salt),
            "resident": pseudonym("R", resident_code, salt),
            "week": week_start(issued_at),
            "code": code,
            "severity": severity,
            "duration_hours": duration_hours,
            "hours_served": round(max(hours_served, 0), 1),
            "issued_by_role": issued_by_role,
            "confirmed_by_role": confirmed_by_role,
            "outcome": outcome_of(status, ends_at, now),
            "appeal": appeal,
        }
    )


def aggregate(records: list[dict], minimum: int) -> dict:
    """Totals overall and per issuing role, with small cells suppressed."""

    def count(rs: list[dict], **where) -> int:
        return sum(all(r[k] == v for k, v in where.items()) for r in rs)

    by_role = {}
    for role in sorted({r["issued_by_role"] for r in records}):
        rs = [r for r in records if r["issued_by_role"] == role]
        applied = [r for r in rs if r["outcome"] in ("active", "ended", "overturned")]
        by_role[role] = {
            "issued": suppress(len(rs), minimum),
            "applied": suppress(len(applied), minimum),
            "rejected": suppress(count(rs, outcome="rejected"), minimum),
            "overturned_on_appeal": suppress(count(rs, outcome="overturned"), minimum),
            "appealed": suppress(sum(r["appeal"] != "none" for r in rs), minimum),
        }
    codes = Counter(r["code"] for r in records)
    return {
        "total_records": suppress(len(records), minimum),
        "by_issuing_role": by_role,
        "by_code": {c: suppress(n, minimum) for c, n in sorted(codes.items())},
    }
