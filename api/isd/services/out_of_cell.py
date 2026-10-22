"""Out-of-cell log: facility-entered (or ingested) minutes per resident per day. Append-only."""

from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from isd.models import OutOfCellLog, Resident
from isd.services.audit import Actor, append_audit


def record(
    session: Session,
    actor: Actor,
    resident_id: int,
    day: date,
    minutes: int,
    source: str,
    now: datetime,
) -> OutOfCellLog:
    if not 0 <= minutes <= 1440:
        raise ValueError("minutes must be between 0 and 1440")
    if day > now.date():
        raise ValueError("cannot record a future day")
    resident = session.get(Resident, resident_id)
    if resident is None:
        raise LookupError("resident not found")
    row = OutOfCellLog(
        resident_id=resident_id,
        day=day,
        minutes=minutes,
        source=source,
        entered_by=actor.id,
        created_at=now,
    )
    session.add(row)
    session.flush()
    append_audit(
        session,
        actor,
        "out_of_cell_entered",
        "resident",
        resident_id,
        reason_code="OUT_OF_CELL",
        payload={"day": day.isoformat(), "minutes": minutes, "source": source},
    )
    return row


def by_day(session: Session, resident_id: int, first: date, last: date) -> dict[date, int]:
    """Latest entry per day (a correction is simply a later row)."""
    rows = session.execute(
        select(OutOfCellLog)
        .where(
            OutOfCellLog.resident_id == resident_id,
            OutOfCellLog.day >= first,
            OutOfCellLog.day <= last,
        )
        .order_by(OutOfCellLog.id)
    ).scalars()
    return {r.day: r.minutes for r in rows}


def window(
    session: Session, resident_id: int, today: date, days: int
) -> list[tuple[date, int | None]]:
    first = today - timedelta(days=days - 1)
    got = by_day(session, resident_id, first, today)
    return [(first + timedelta(days=i), got.get(first + timedelta(days=i))) for i in range(days)]


def below_minimum(session: Session, now: datetime, within_days: int = 3) -> list[dict]:
    """Residents whose most recent finished day (yesterday or a little earlier) is under the
    configured minimum. A day with nothing recorded is not counted here (the welfare check
    reports unrecorded days separately)."""
    from isd.models import DeviceAssignment
    from isd.services.config_store import get_current

    minimum = int(get_current(session, "compliance").payload["min_out_of_cell_minutes_per_day"])
    today = now.date()
    out = []
    residents = session.execute(
        select(Resident.id, Resident.code)
        .join(DeviceAssignment, DeviceAssignment.resident_id == Resident.id)
        .group_by(Resident.id, Resident.code)
        .order_by(Resident.code)
    ).all()
    for rid, code in residents:
        recorded = [
            (d, m)
            for d, m in window(session, rid, today - timedelta(days=1), within_days)
            if m is not None
        ]
        if recorded and recorded[-1][1] < minimum:
            out.append(
                {
                    "resident_id": rid,
                    "resident": code,
                    "day": recorded[-1][0].isoformat(),
                    "minutes": recorded[-1][1],
                    "minimum": minimum,
                }
            )
    return out
