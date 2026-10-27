"""The unit schedule: blocks for indoor and outdoor recreation, programs and visits, per unit and
day. A day with no blocks of its own uses the template in config (`rec`); staff can add or cancel
blocks, which makes the day explicit. Eligibility to sign up is decided by get_entitlements
through each block's `required_feature` (so outdoor time at tiers 9 and 10 comes from the tier
matrix, and indoor time is baseline)."""

from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from isd.models import BLOCK_KINDS, Cell, DeviceAssignment, RecBooking, ScheduleBlock
from isd.services import facility_model as facility
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


def _hhmm(minutes: int) -> str | None:
    return None if not 0 <= minutes < 24 * 60 else f"{minutes // 60:02d}:{minutes % 60:02d}"


def line_limits(cfg: dict) -> dict[str, int]:
    """Most blocks of each kind that may run at once on a line."""
    return {
        "indoor": max(1, cfg["rooms_per_line"]),
        "outdoor": max(1, min(cfg["max_concurrent_out_per_line"], cfg["outdoor_rooms_per_line"])),
    }


def _minutes(start: str) -> int:
    h, m = start.split(":")
    return int(h) * 60 + int(m)


def unit_template(session: Session, unit: str) -> list[dict]:
    """The blocks for one unit-day. A line of the facility model gets recreation per floor: each
    floor starts `stagger_minutes` after the one below it, and a block is pushed later until no
    more blocks than the line has room for run at once: the yards are limited by the line's
    concurrency limit, the day rooms only by how many day rooms the line has (the baseline
    out-of-cell time is never held back by the concurrency limit). Programs and visits are shared
    by every floor. Any other unit gets the plain template, one set of blocks (floor 0)."""
    base = [{**b, "floor": 0} for b in template(session)]
    line = facility.line_of_unit(session, unit)
    if line is None:
        return base
    cfg = facility.settings(session)["rec"]
    allowed = line_limits(cfg)
    step = max(5, cfg["stagger_minutes"])
    out = [b for b in base if b["kind"] in ("program", "visit")]  # shared by every floor
    placed: dict[str, list[tuple[int, int]]] = {"indoor": [], "outdoor": []}  # (start, end)
    levels = facility.floor_levels(session, line.id)
    for slot in sorted(
        (b for b in base if b["kind"] in ("indoor", "outdoor")), key=lambda b: _minutes(b["start"])
    ):
        for index, level in enumerate(levels):
            start = _minutes(slot["start"]) + index * cfg["stagger_minutes"]
            kind_placed = placed[slot["kind"]]
            while (
                sum(1 for a, b in kind_placed if a < start + slot["minutes"] and start < b)
                >= allowed[slot["kind"]]
            ):
                start += step
            text = _hhmm(start)
            if text is None or start + slot["minutes"] > 24 * 60:
                continue  # no room left in the day for this floor's block
            kind_placed.append((start, start + slot["minutes"]))
            out.append({**slot, "start": text, "floor": level, "capacity": cfg["room_capacity"]})
    return sorted(out, key=lambda b: (b["start"], b["kind"], b["floor"]))


def _area_ids(session: Session, unit: str) -> dict[tuple[str, int], int]:
    """Which recreation room each (kind, floor) uses: floors take the line's rooms in turn."""
    line = facility.line_of_unit(session, unit)
    if line is None:
        return {}
    out: dict[tuple[str, int], int] = {}
    levels = facility.floor_levels(session, line.id)
    for kind in ("indoor", "outdoor"):
        rooms = facility.rec_areas(session, line.id, kind)
        for index, level in enumerate(levels):
            if rooms:
                out[(kind, level)] = rooms[index % len(rooms)].id
    return out


def max_concurrent_out(blocks: list[tuple[str, int]]) -> int:
    """Most recreation blocks running at once, from (start HH:MM, minutes) pairs."""
    spans = []
    for start, minutes in blocks:
        h, m = start.split(":")
        a = int(h) * 60 + int(m)
        spans.append((a, a + minutes))
    return max((sum(1 for a, b in spans if a <= t < b) for t, _ in spans), default=0)


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
    blocks = unit_template(session, unit)
    areas = _area_ids(session, unit)
    for b in blocks:
        area = areas.get((b["kind"], b["floor"]))
        session.add(ScheduleBlock(unit=unit, day=day, created_at=now, rec_area_id=area, **b))
    session.flush()
    return len(blocks)


def generate(session: Session, now: datetime, days_ahead: int | None = None) -> int:
    """Daily job: make the next days explicit for every unit. Safe to repeat."""
    ahead = days_ahead or get_current(session, "rec").payload["generate_days_ahead"]
    made = 0
    for unit in units(session):
        for i in range(ahead + 1):
            made += ensure_day(session, unit, now.date() + timedelta(days=i), now)
    return made


def blocks_for(session: Session, unit: str, day: date, floor: int | None = None) -> list[dict]:
    """The day's blocks: its own if it has any, otherwise the template (not yet saved). With
    `floor`, only the blocks for that floor and the ones shared by every floor."""
    q = select(ScheduleBlock).where(ScheduleBlock.unit == unit, ScheduleBlock.day == day)
    if floor is not None:
        q = q.where(ScheduleBlock.floor.in_((0, floor)))
    rows = session.execute(q.order_by(ScheduleBlock.start, ScheduleBlock.kind)).scalars().all()
    if not rows and not has_blocks(session, unit, day):
        return [
            {"id": None, "unit": unit, "day": day, "status": "scheduled", **b}
            for b in unit_template(session, unit)
            if floor is None or b["floor"] in (0, floor)
        ]
    return [
        {
            "id": r.id,
            "unit": r.unit,
            "day": r.day,
            "kind": r.kind,
            "floor": r.floor,
            "rec_area_id": r.rec_area_id,
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
    floor: int = 0,
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
    if floor < 0 or floor > 20:
        raise ScheduleError("BAD_BLOCK", "check the floor")
    ensure_day(session, unit, day, now)  # keep the rest of the template for that day
    if session.execute(
        select(ScheduleBlock.id).where(
            ScheduleBlock.unit == unit,
            ScheduleBlock.day == day,
            ScheduleBlock.kind == kind,
            ScheduleBlock.start == start,
            ScheduleBlock.floor == floor,
        )
    ).first():
        raise ScheduleError("DUPLICATE", "there is already a block at that time")
    _check_line_limit(session, unit, day, kind, start, minutes)
    feature = required_feature if required_feature is not None else KIND_FEATURE.get(kind)
    row = ScheduleBlock(
        unit=unit,
        day=day,
        kind=kind,
        floor=floor,
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


def _check_line_limit(
    session: Session, unit: str, day: date, kind: str, start: str, minutes: int
) -> None:
    """On a line of the facility model, no more blocks of a kind than the line allows may run at
    once: yards by the concurrency limit, day rooms by how many day rooms there are. The baseline
    out-of-cell time is never reduced by this; it only refuses one more block that would not fit."""
    if kind not in ("indoor", "outdoor") or facility.line_of_unit(session, unit) is None:
        return
    limit = line_limits(facility.settings(session)["rec"])[kind]
    existing = session.execute(
        select(ScheduleBlock.start, ScheduleBlock.minutes).where(
            ScheduleBlock.unit == unit,
            ScheduleBlock.day == day,
            ScheduleBlock.kind == kind,
            ScheduleBlock.status == "scheduled",
        )
    ).all()
    if max_concurrent_out([(a, b) for a, b in existing] + [(start, minutes)]) > limit:
        raise ScheduleError(
            "LINE_BUSY", f"no more than {limit} {kind} blocks can run at once on this line"
        )


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
