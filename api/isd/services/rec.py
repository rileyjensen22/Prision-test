"""Out-of-cell time sign-up: recreation, programs and visits from the unit's schedule.
Eligibility comes from get_entitlements through each block's required feature."""

from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from isd.models import RecBooking, ScheduleBlock
from isd.services import schedule
from isd.services.entitlement_service import get_entitlements


class RecDenied(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _allowed(block: dict, ent) -> bool:
    feature = block["required_feature"]
    return True if feature is None else ent.features[feature].allowed


def day_view(session: Session, resident_id: int, day: date, now: datetime) -> dict:
    unit = schedule.unit_of(session, resident_id)
    ent = get_entitlements(session, resident_id, now)
    blocks = schedule.blocks_for(session, unit, day)
    counts = schedule.booked_counts(session, unit, day)
    mine = {
        b.block_id
        for b in session.execute(
            select(RecBooking).where(RecBooking.resident_id == resident_id, RecBooking.day == day)
        ).scalars()
        if b.block_id is not None
    }
    return {
        "day": day.isoformat(),
        "unit": unit,
        "baseline_minutes": ent.features["out_of_cell_minimum"].limits["minutes_per_day"],
        "slots": [
            {
                "slot": b["start"],
                "kind": b["kind"],
                "title": b["title"],
                "minutes": b["minutes"],
                "block_id": b["id"],
                "cancelled": b["status"] == "cancelled",
                "allowed": _allowed(b, ent) and b["status"] == "scheduled",
                "booked": b["id"] in mine,
                "spaces": max(0, b["capacity"] - counts.get(b["id"], 0)),
            }
            for b in blocks
        ],
    }


def _find_block(session: Session, unit: str, day: date, slot: str, block_id: int | None):
    q = select(ScheduleBlock).where(ScheduleBlock.unit == unit, ScheduleBlock.day == day)
    if block_id is not None:
        q = q.where(ScheduleBlock.id == block_id)
    else:
        q = q.where(ScheduleBlock.start == slot)
    return session.execute(q.order_by(ScheduleBlock.kind).limit(1)).scalar()


def book(
    session: Session,
    resident_id: int,
    day: date,
    slot: str,
    now: datetime,
    block_id: int | None = None,
) -> RecBooking:
    if not now.date() <= day <= now.date() + timedelta(days=7):
        raise RecDenied("BAD_DAY", "book today or up to a week ahead")
    unit = schedule.unit_of(session, resident_id)
    schedule.ensure_day(session, unit, day, now)  # a template day becomes real when first used
    block = _find_block(session, unit, day, slot, block_id)
    if block is None:
        raise RecDenied("BAD_SLOT", "no such slot")
    if block.status != "scheduled":
        raise RecDenied("CANCELLED", "that block was cancelled")
    feature = block.required_feature
    if feature and not get_entitlements(session, resident_id, now).features[feature].allowed:
        raise RecDenied("FEATURE_LOCKED", "that is locked for you right now")
    taken = session.execute(select(func.count()).where(RecBooking.block_id == block.id)).scalar()
    if taken >= block.capacity:
        raise RecDenied("FULL", "that slot is full")
    if session.execute(
        select(RecBooking.id).where(
            RecBooking.resident_id == resident_id, RecBooking.block_id == block.id
        )
    ).first():
        raise RecDenied("ALREADY_BOOKED", "already booked")
    row = RecBooking(
        resident_id=resident_id,
        day=day,
        slot=block.start,
        kind=block.kind,
        block_id=block.id,
        created_at=now,
    )
    session.add(row)
    session.flush()
    return row


def cancel(
    session: Session, resident_id: int, day: date, slot: str, block_id: int | None = None
) -> bool:
    q = select(RecBooking).where(RecBooking.resident_id == resident_id, RecBooking.day == day)
    q = q.where(RecBooking.block_id == block_id) if block_id else q.where(RecBooking.slot == slot)
    row = session.execute(q.limit(1)).scalar()
    if row is None:
        return False
    session.delete(row)
    return True
