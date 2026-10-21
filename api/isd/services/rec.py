"""Out-of-cell time slots (stub). Indoor is baseline; outdoor needs the outdoor_rec feature."""

from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from isd.models import RecBooking
from isd.services.config_store import get_current
from isd.services.entitlement_service import get_entitlements


class RecDenied(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _cfg(session: Session) -> dict:
    return get_current(session, "rec").payload


def day_view(session: Session, resident_id: int, day: date, now: datetime) -> dict:
    cfg = _cfg(session)
    ent = get_entitlements(session, resident_id, now)
    mine = {
        b.slot
        for b in session.execute(
            select(RecBooking).where(RecBooking.resident_id == resident_id, RecBooking.day == day)
        ).scalars()
    }
    counts = dict(
        session.execute(
            select(RecBooking.slot, func.count())
            .where(RecBooking.day == day)
            .group_by(RecBooking.slot)
        ).all()
    )
    outdoor_ok = ent.features["outdoor_rec"].allowed

    def slots(names: list[str], kind: str, allowed: bool):
        return [
            {
                "slot": s,
                "kind": kind,
                "allowed": allowed,
                "booked": s in mine,
                "spaces": max(0, cfg["capacity"] - counts.get(s, 0)),
            }
            for s in names
        ]

    return {
        "day": day.isoformat(),
        "baseline_minutes": ent.features["out_of_cell_minimum"].limits["minutes_per_day"],
        "slots": slots(cfg["indoor_slots"], "indoor", True)
        + slots(cfg["outdoor_slots"], "outdoor", outdoor_ok),
    }


def book(session: Session, resident_id: int, day: date, slot: str, now: datetime) -> RecBooking:
    cfg = _cfg(session)
    if not now.date() <= day <= now.date() + timedelta(days=7):
        raise RecDenied("BAD_DAY", "book today or up to a week ahead")
    kind = (
        "indoor"
        if slot in cfg["indoor_slots"]
        else "outdoor"
        if slot in cfg["outdoor_slots"]
        else None
    )
    if kind is None:
        raise RecDenied("BAD_SLOT", "no such slot")
    if (
        kind == "outdoor"
        and not get_entitlements(session, resident_id, now).features["outdoor_rec"].allowed
    ):
        raise RecDenied("FEATURE_LOCKED", "outdoor recreation is locked")
    taken = session.execute(
        select(func.count()).where(RecBooking.day == day, RecBooking.slot == slot)
    ).scalar()
    if taken >= cfg["capacity"]:
        raise RecDenied("FULL", "that slot is full")
    if session.execute(
        select(RecBooking.id).where(
            RecBooking.resident_id == resident_id, RecBooking.day == day, RecBooking.slot == slot
        )
    ).first():
        raise RecDenied("ALREADY_BOOKED", "already booked")
    row = RecBooking(resident_id=resident_id, day=day, slot=slot, kind=kind, created_at=now)
    session.add(row)
    session.flush()
    return row


def cancel(session: Session, resident_id: int, day: date, slot: str) -> bool:
    row = session.execute(
        select(RecBooking).where(
            RecBooking.resident_id == resident_id, RecBooking.day == day, RecBooking.slot == slot
        )
    ).scalar()
    if row is None:
        return False
    session.delete(row)
    return True
