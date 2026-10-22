"""The unit schedule: blocks for indoor and outdoor recreation, programs and visits, per unit and
day. A day with no blocks of its own uses the template in config (`rec`); staff can add or cancel
blocks, which makes the day explicit. Eligibility to sign up is decided by get_entitlements
through each block's `required_feature` (so outdoor time at tiers 9 and 10 comes from the tier
matrix, and indoor time is baseline)."""

from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from isd.models import BLOCK_KINDS, Cell, DeviceAssignment, RecBooking, ScheduleBlock
from isd.services.audit import Actor, append_audit
from isd.services.config_store import get_current

DEFAULT_UNIT = "A"
KIND_FEATURE = {"indoor": "out_of_cell_minimum", "outdoor": "outdoor_rec", "visit": None}
MIN_REASON = 5


class ScheduleError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def unit_of(session: Session, resident_id: int) -> str:
    cell = session.execute(
        select(Cell.unit)
        .join(DeviceAssignment, DeviceAssignment.cell_id == Cell.id)
        .where(DeviceAssignment.resident_id == resident_id)
        .order_by(DeviceAssignment.assigned_at.desc(), DeviceAssignment.id.desc())
        .limit(1)
    ).scalar()
    return cell or DEFAULT_UNIT


def units(session: Session) -> list[str]:
    return sorted({u for u in session.execute(select(Cell.unit)).scalars()} | {DEFAULT_UNIT})


def template(session: Session) -> list[dict]:
    cfg = get_current(session, "rec").payload
    out = [
        {
            "kind": "indoor",
            "start": s,
            "minutes": cfg["indoor_minutes"],
            "capacity": cfg["capacity"],
            "title": None,
            "required_feature": KIND_FEATURE["indoor"],
        }
        for s in cfg["indoor_slots"]
    ]
    out += [
        {
            "kind": "outdoor",
            "start": s,
            "minutes": cfg["outdoor_minutes"],
            "capacity": cfg["capacity"],
            "title": None,
            "required_feature": KIND_FEATURE["outdoor"],
        }
        for s in cfg["outdoor_slots"]
    ]
    out += [
        {
            "kind": "program",
            "start": p["start"],
            "minutes": p["minutes"],
            "capacity": p["capacity"],
            "title": p["title"],
            "required_feature": p.get("feature", "basic_education"),
        }
        for p in cfg["programs"]
    ]
    out += [
        {
            "kind": "visit",
            "start": v["start"],
            "minutes": v["minutes"],
            "capacity": v["capacity"],
            "title": v["title"],
            "required_feature": None,
        }
        for v in cfg["visits"]
    ]
    return sorted(out, key=lambda b: (b["start"], b["kind"]))


def has_blocks(session: Session, unit: str, day: date) -> bool:
    return (
        session.execute(
            select(ScheduleBlock.id).where(ScheduleBlock.unit == unit, ScheduleBlock.day == day)
        ).first()
        is not None
    )


def ensure_day(session: Session, unit: str, day: date, now: datetime) -> int:
    """Makes a unit-day explicit from the template. Does nothing if it already has blocks."""
    if has_blocks(session, unit, day):
        return 0
    for b in template(session):
        session.add(ScheduleBlock(unit=unit, day=day, created_at=now, **b))
    session.flush()
    return len(template(session))


def generate(session: Session, now: datetime, days_ahead: int | None = None) -> int:
    """Daily job: make the next days explicit for every unit. Safe to repeat."""
    ahead = days_ahead or get_current(session, "rec").payload["generate_days_ahead"]
    made = 0
    for unit in units(session):
        for i in range(ahead + 1):
            made += ensure_day(session, unit, now.date() + timedelta(days=i), now)
    return made


def blocks_for(session: Session, unit: str, day: date) -> list[dict]:
    """The day's blocks: its own if it has any, otherwise the template (not yet saved)."""
    rows = (
        session.execute(
            select(ScheduleBlock)
            .where(ScheduleBlock.unit == unit, ScheduleBlock.day == day)
            .order_by(ScheduleBlock.start, ScheduleBlock.kind)
        )
        .scalars()
        .all()
    )
    if not rows:
        return [
            {"id": None, "unit": unit, "day": day, "status": "scheduled", **b}
            for b in template(session)
        ]
    return [
        {
            "id": r.id,
            "unit": r.unit,
            "day": r.day,
            "kind": r.kind,
            "start": r.start,
            "minutes": r.minutes,
            "capacity": r.capacity,
            "title": r.title,
            "required_feature": r.required_feature,
            "status": r.status,
        }
        for r in rows
    ]


def booked_counts(session: Session, unit: str, day: date) -> dict[int, int]:
    return dict(
        session.execute(
            select(RecBooking.block_id, func.count())
            .join(ScheduleBlock, ScheduleBlock.id == RecBooking.block_id)
            .where(ScheduleBlock.unit == unit, ScheduleBlock.day == day)
            .group_by(RecBooking.block_id)
        ).all()
    )


def _valid_time(start: str) -> bool:
    hh, _, mm = start.partition(":")
    return hh.isdigit() and mm.isdigit() and len(start) == 5 and int(hh) < 24 and int(mm) < 60


def add_block(
    session: Session,
    actor: Actor,
    unit: str,
    day: date,
    kind: str,
    start: str,
    minutes: int,
    capacity: int,
    title: str | None,
    required_feature: str | None,
    reason: str,
    now: datetime,
) -> ScheduleBlock:
    if kind not in BLOCK_KINDS:
        raise ScheduleError("BAD_KIND", "kind must be indoor, outdoor, program or visit")
    if not _valid_time(start) or minutes < 1 or capacity < 1 or minutes > 600 or capacity > 200:
        raise ScheduleError("BAD_BLOCK", "check the start time, length and capacity")
    if kind in ("program", "visit") and not (title or "").strip():
        raise ScheduleError("BAD_BLOCK", "programs and visits need a title")
    if len(reason.strip()) < MIN_REASON:
        raise ScheduleError("REASON_REQUIRED", "give a reason for the change")
    if day < now.date():
        raise ScheduleError("PAST", "the schedule for a past day cannot be changed")
    ensure_day(session, unit, day, now)  # keep the rest of the template for that day
    if session.execute(
        select(ScheduleBlock.id).where(
            ScheduleBlock.unit == unit,
            ScheduleBlock.day == day,
            ScheduleBlock.kind == kind,
            ScheduleBlock.start == start,
        )
    ).first():
        raise ScheduleError("DUPLICATE", "there is already a block at that time")
    feature = required_feature if required_feature is not None else KIND_FEATURE.get(kind)
    row = ScheduleBlock(
        unit=unit,
        day=day,
        kind=kind,
        start=start,
        minutes=minutes,
        capacity=capacity,
        title=(title or "").strip() or None,
        required_feature=feature,
        created_by=actor.id,
        created_at=now,
    )
    session.add(row)
    session.flush()
    append_audit(
        session,
        actor,
        "schedule_block_added",
        "schedule_block",
        row.id,
        "SCHEDULE",
        payload={
            "unit": unit,
            "day": day.isoformat(),
            "kind": kind,
            "start": start,
            "reason": reason.strip(),
        },
    )
    return row


def cancel_block(
    session: Session, actor: Actor, block_id: int, reason: str, now: datetime
) -> ScheduleBlock:
    b = session.get(ScheduleBlock, block_id)
    if b is None:
        raise ScheduleError("NOT_FOUND", "block not found")
    if len(reason.strip()) < MIN_REASON:
        raise ScheduleError("REASON_REQUIRED", "give a reason for the change")
    if b.status == "cancelled":
        return b
    b.status = "cancelled"
    append_audit(
        session,
        actor,
        "schedule_block_cancelled",
        "schedule_block",
        b.id,
        "SCHEDULE",
        payload={
            "unit": b.unit,
            "day": b.day.isoformat(),
            "kind": b.kind,
            "start": b.start,
            "reason": reason.strip(),
        },
    )
    return b


def admin_view(session: Session, unit: str, day: date) -> dict:
    blocks = blocks_for(session, unit, day)
    counts = booked_counts(session, unit, day)
    return {
        "unit": unit,
        "day": day.isoformat(),
        "explicit": has_blocks(session, unit, day),
        "blocks": [
            {**b, "day": b["day"].isoformat(), "booked": counts.get(b["id"], 0)} for b in blocks
        ],
    }
