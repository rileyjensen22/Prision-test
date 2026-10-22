"""Out-of-cell movement: officers tap residents out and in; time is worked out from those events.

Every change is a new row (the event table is append-only). Each tap-in also writes the day's
total into the out-of-cell log (a later entry for a day replaces the earlier one), so the minimum
-time flags and the dashboard see it. Bulk actions apply to many residents at once and report
each one's outcome, so one problem never blocks the rest.
"""

import csv
import io
from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from isd.engine.movement import (
    Interval,
    attendance,
    close_intervals,
    minutes_by_day,
    overlap_minutes,
)
from isd.models import (
    Cell,
    DeviceAssignment,
    OutOfCellEvent,
    RecBooking,
    Resident,
    ScheduleBlock,
)
from isd.services import out_of_cell, schedule
from isd.services.audit import Actor, append_audit
from isd.services.config_store import get_current

ACTIVITIES = ("indoor", "outdoor", "program", "visit", "other")
MAX_BACKDATE = timedelta(hours=24)
MAX_BULK = 200


class MovementError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _events(session: Session, resident_id: int) -> list[OutOfCellEvent]:
    return list(
        session.execute(
            select(OutOfCellEvent)
            .where(OutOfCellEvent.resident_id == resident_id)
            .order_by(OutOfCellEvent.at, OutOfCellEvent.id)
        ).scalars()
    )


def _state(events: list[OutOfCellEvent]) -> OutOfCellEvent | None:
    """The event that put the resident out, if they are out now."""
    out = None
    for e in events:
        if e.event == "out" and out is None:
            out = e
        elif e.event == "in":
            out = None
    return out


def _check_time(at: datetime | None, now: datetime, last: OutOfCellEvent | None) -> datetime:
    when = at or now
    if when > now + timedelta(minutes=1):
        raise MovementError("FUTURE", "that time has not happened yet")
    if when < now - MAX_BACKDATE:
        raise MovementError("TOO_OLD", "record movements within a day of when they happened")
    if last is not None and when < last.at:
        raise MovementError("OUT_OF_ORDER", "that is before the resident's last movement")
    return when


def tap_out(
    session: Session,
    actor: Actor,
    resident_id: int,
    activity: str,
    now: datetime,
    block_id: int | None = None,
    at: datetime | None = None,
) -> OutOfCellEvent:
    if activity not in ACTIVITIES:
        raise MovementError("BAD_ACTIVITY", "choose what the resident is out for")
    if session.get(Resident, resident_id) is None:
        raise MovementError("NOT_FOUND", "resident not found")
    events = _events(session, resident_id)
    if _state(events) is not None:
        raise MovementError("ALREADY_OUT", "the resident is already out of the cell")
    if block_id is not None and session.get(ScheduleBlock, block_id) is None:
        raise MovementError("BAD_BLOCK", "no such block")
    row = OutOfCellEvent(
        resident_id=resident_id,
        event="out",
        at=_check_time(at, now, events[-1] if events else None),
        activity=activity,
        block_id=block_id,
        entered_by=actor.id,
        created_at=now,
    )
    session.add(row)
    session.flush()
    return row


def tap_in(
    session: Session,
    actor: Actor,
    resident_id: int,
    now: datetime,
    at: datetime | None = None,
) -> OutOfCellEvent:
    events = _events(session, resident_id)
    out = _state(events)
    if out is None:
        raise MovementError("NOT_OUT", "the resident is not out of the cell")
    when = _check_time(at, now, events[-1])
    row = OutOfCellEvent(
        resident_id=resident_id,
        event="in",
        at=when,
        activity=out.activity,
        block_id=out.block_id,
        entered_by=actor.id,
        created_at=now,
    )
    session.add(row)
    session.flush()
    _write_day_totals(session, actor, resident_id, out.at, when, now)
    return row


def _write_day_totals(
    session: Session, actor: Actor, resident_id: int, start: datetime, end: datetime, now: datetime
) -> None:
    """Records each touched day's total in the out-of-cell log (a correction row if it changed)."""
    for day in minutes_by_day([(start, end)]):
        total = actual_minutes(session, resident_id, day, now)
        if out_of_cell.by_day(session, resident_id, day, day).get(day) != total:
            out_of_cell.record(session, actor, resident_id, day, total, "facility", now)


def _bulk(session: Session, ids: list[int], fn) -> list[dict]:
    if not 1 <= len(ids) <= MAX_BULK:
        raise MovementError("BAD_BULK", f"choose between 1 and {MAX_BULK} residents")
    results = []
    for rid in dict.fromkeys(ids):  # in order, without repeats
        try:
            with session.begin_nested():
                fn(rid)
            results.append({"resident_id": rid, "ok": True, "code": None})
        except MovementError as e:
            results.append({"resident_id": rid, "ok": False, "code": e.code})
    return results


def bulk_out(
    session: Session,
    actor: Actor,
    resident_ids: list[int],
    activity: str,
    now: datetime,
    block_id: int | None = None,
) -> list[dict]:
    return _bulk(
        session, resident_ids, lambda rid: tap_out(session, actor, rid, activity, now, block_id)
    )


def bulk_in(session: Session, actor: Actor, resident_ids: list[int], now: datetime) -> list[dict]:
    return _bulk(session, resident_ids, lambda rid: tap_in(session, actor, rid, now))


# ---------------- reading it back ----------------
def intervals(session: Session, resident_id: int, now: datetime) -> list[Interval]:
    return close_intervals([(e.event, e.at) for e in _events(session, resident_id)], now)


def actual_minutes(session: Session, resident_id: int, day: date, now: datetime) -> int:
    return minutes_by_day(intervals(session, resident_id, now)).get(day, 0)


def _unit_map(session: Session) -> dict[int, str]:
    rows = session.execute(
        select(DeviceAssignment.resident_id, Cell.unit)
        .join(Cell, Cell.id == DeviceAssignment.cell_id)
        .order_by(DeviceAssignment.assigned_at, DeviceAssignment.id)
    ).all()
    return {rid: unit for rid, unit in rows}  # the latest assignment wins


def who_is_out(session: Session, now: datetime, unit: str | None = None) -> list[dict]:
    units = _unit_map(session)
    latest: dict[int, OutOfCellEvent] = {}
    for e in session.execute(
        select(OutOfCellEvent).order_by(OutOfCellEvent.at, OutOfCellEvent.id)
    ).scalars():
        latest[e.resident_id] = e
    out = []
    codes = dict(session.execute(select(Resident.id, Resident.code)).all())
    for rid, e in latest.items():
        if e.event != "out":
            continue
        u = units.get(rid, schedule.DEFAULT_UNIT)
        if unit and u != unit:
            continue
        out.append(
            {
                "resident_id": rid,
                "resident": codes[rid],
                "unit": u,
                "activity": e.activity,
                "since": e.at.isoformat(),
                "minutes": max(0, int((now - e.at).total_seconds() // 60)),
            }
        )
    return sorted(out, key=lambda r: r["since"])


def _window(block: ScheduleBlock, tz) -> Interval:
    hh, mm = (int(x) for x in block.start.split(":"))
    start = datetime.combine(block.day, time(hh, mm), tzinfo=tz)
    return start, start + timedelta(minutes=block.minutes)


def discrepancies(session: Session, day: date, now: datetime, unit: str | None = None) -> dict:
    """Scheduled versus actual for a day: each block's sign-ups against who was actually out
    during it, and each resident's booked minutes against the minutes they were out."""
    minimum = int(get_current(session, "compliance").payload["min_out_of_cell_minutes_per_day"])
    units = _unit_map(session)
    codes = dict(session.execute(select(Resident.id, Resident.code)).all())
    blocks = (
        session.execute(
            select(ScheduleBlock)
            .where(ScheduleBlock.day == day, ScheduleBlock.status == "scheduled")
            .order_by(ScheduleBlock.unit, ScheduleBlock.start)
        )
        .scalars()
        .all()
    )
    if unit:
        blocks = [b for b in blocks if b.unit == unit]
    cache: dict[int, list[Interval]] = {}

    def ivals(rid: int) -> list[Interval]:
        if rid not in cache:
            cache[rid] = intervals(session, rid, now)
        return cache[rid]

    per_resident: dict[int, dict] = {}
    block_rows = []
    for b in blocks:
        window = _window(b, now.tzinfo)
        bookers = (
            session.execute(select(RecBooking.resident_id).where(RecBooking.block_id == b.id))
            .scalars()
            .all()
        )
        missed, partial, attended = [], [], []
        for rid in bookers:
            label = attendance(ivals(rid), window, now)
            got = overlap_minutes(ivals(rid), window)
            rec = per_resident.setdefault(
                rid, {"resident_id": rid, "resident": codes[rid], "scheduled_minutes": 0}
            )
            rec["scheduled_minutes"] += b.minutes
            entry = {"resident_id": rid, "resident": codes[rid], "minutes": got}
            if label == "missed":
                missed.append(entry)
            elif label == "partial":
                partial.append(entry)
            elif label == "attended":
                attended.append(entry)
        block_rows.append(
            {
                "block_id": b.id,
                "unit": b.unit,
                "kind": b.kind,
                "start": b.start,
                "title": b.title,
                "minutes": b.minutes,
                "booked": len(bookers),
                "attended": len(attended),
                "partial": len(partial),
                "missed": len(missed),
                "missed_residents": [m["resident"] for m in missed],
            }
        )
    day_over = now.date() > day
    residents = []
    pool = {r for r, u in units.items() if not unit or u == unit} | set(per_resident)
    for rid in sorted(pool, key=lambda r: codes.get(r, "")):
        if unit and units.get(rid, schedule.DEFAULT_UNIT) != unit and rid not in per_resident:
            continue
        actual = minutes_by_day(ivals(rid)).get(day, 0)
        scheduled = per_resident.get(rid, {}).get("scheduled_minutes", 0)
        below = day_over and actual < minimum
        short = day_over and scheduled > 0 and actual * 2 < scheduled
        if not (scheduled or below or actual):
            continue
        residents.append(
            {
                "resident_id": rid,
                "resident": codes[rid],
                "unit": units.get(rid, schedule.DEFAULT_UNIT),
                "scheduled_minutes": scheduled,
                "actual_minutes": actual,
                "below_minimum": below,
                "short_of_schedule": short,
            }
        )
    return {
        "day": day.isoformat(),
        "unit": unit,
        "minimum": minimum,
        "blocks": block_rows,
        "residents": residents,
    }


def export_day(
    session: Session, actor: Actor, day: date, now: datetime, unit: str | None, fmt: str
) -> tuple[str, str]:
    """The day's records as CSV or JSON text. Exporting is audit-logged."""
    report = discrepancies(session, day, now, unit)
    append_audit(
        session,
        actor,
        "out_of_cell_export",
        "day",
        day.isoformat(),
        "OUT_OF_CELL_EXPORT",
        payload={"unit": unit, "format": fmt, "rows": len(report["residents"])},
    )
    if fmt == "json":
        import json

        return json.dumps(report, indent=2), "application/json"
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(
        [
            "day",
            "unit",
            "resident",
            "scheduled_minutes",
            "actual_minutes",
            "below_minimum",
            "short_of_schedule",
        ]
    )
    for r in report["residents"]:
        w.writerow(
            [
                report["day"],
                r["unit"],
                r["resident"],
                r["scheduled_minutes"],
                r["actual_minutes"],
                r["below_minimum"],
                r["short_of_schedule"],
            ]
        )
    return buf.getvalue(), "text/csv"
