"""Pure helpers for the outcomes dashboard and researcher export.

Evaluation only (invariant 17): nothing in the engine, the entitlement code, points, sanctions or
tiers imports this package, and it produces no per-person score. Small groups are suppressed.
"""

from datetime import datetime

FORBIDDEN_FIELDS = frozenset(
    {
        "resident_code",
        "display_name",
        "name",
        "cell",
        "device",
        "contact",
        "phone",
        "id",
        "resident_id",
    }
)


def cohort_label(when: datetime) -> str:
    return f"{when.year}-Q{(when.month - 1) // 3 + 1}"


def band(count: int, edges: tuple[int, ...]) -> str:
    """'0', then '1-4' style ranges between the edges, then 'N+'. Never an exact count."""
    if count <= 0:
        return "0"
    lo = None
    for edge in edges:
        if count < edge:
            return f"{lo}-{edge - 1}" if lo is not None else f"1-{edge - 1}"
        lo = edge
    return f"{edges[-1]}+"


def rate_per_100(events: int, exposure_weeks: float) -> float | None:
    return round(100 * events / exposure_weeks, 1) if exposure_weeks else None


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 2)


def summarize_cohort(label: str, rows: list[dict], minimum: int) -> dict:
    n = len(rows)
    if n < minimum:
        return {"cohort": label, "residents": f"<{minimum}"}
    weeks = sum(r["weeks"] for r in rows)
    return {
        "cohort": label,
        "residents": n,
        "share_promoted": round(sum(r["tier_now"] > r["tier_start"] for r in rows) / n, 2),
        "mean_tier_change": _mean([r["tier_now"] - r["tier_start"] for r in rows]),
        "share_completed_a_course": round(sum(r["courses"] > 0 for r in rows) / n, 2),
        "mean_courses_completed": _mean([r["courses"] for r in rows]),
        "contacts_per_week": round(sum(r["contacts"] for r in rows) / weeks, 2) if weeks else None,
        "sanctions_per_100_weeks": rate_per_100(sum(r["sanctions"] for r in rows), weeks),
    }


def cohort_labels_for_export(counts: dict[str, int], minimum: int) -> dict[str, str]:
    """Cohorts too small to be anonymous are merged into one 'OTHER' group."""
    return {c: (c if n >= minimum else "OTHER") for c, n in counts.items()}


def assert_no_identifiers(rows: list[dict], forbidden: list[str]) -> None:
    """Refuses an export that has an identifying field name or contains a known code or name."""
    for row in rows:
        bad = FORBIDDEN_FIELDS & set(row)
        if bad:
            raise ValueError(f"identifying field in export: {sorted(bad)}")
    text = repr(rows).lower()
    for value in forbidden:
        if value and value.lower() in text:
            raise ValueError("identifier found in export")
