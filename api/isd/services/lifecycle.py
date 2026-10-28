"""Vacating (release or move out) and transferring a resident. Both are one audited step.

Nothing is deleted. The assignment is closed (`ended_at`), the resident keeps their record,
points, ledgers and history, and the cell and device become free for the next person. Anything
that only makes sense while the resident is on the unit is closed or cancelled with them.
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from isd.models import (
    Cell,
    Device,
    DeviceAssignment,
    KeepSeparate,
    MirrorSession,
    RecBooking,
    Resident,
    VideoBooking,
    WelfareFlag,
)
from isd.services.audit import Actor, append_audit
from isd.services.intake import IntakeError, _find_place


class LifecycleError(IntakeError):
    pass


@dataclass
class Placement:
    resident_id: int
    resident_code: str
    cell_code: str
    device_code: str


def _open_assignment(session: Session, resident_id: int) -> DeviceAssignment:
    row = session.execute(
        select(DeviceAssignment).where(
            DeviceAssignment.resident_id == resident_id, DeviceAssignment.ended_at.is_(None)
        )
    ).scalar()
    if row is None:
        raise LifecycleError("NOT_ASSIGNED", "this resident is not in a cell right now")
    return row


def _resident(session: Session, resident_id: int) -> Resident:
    r = session.get(Resident, resident_id)
    if r is None:
        raise LifecycleError("NOT_FOUND", "resident not found")
    return r


def _reason(reason: str) -> str:
    if len(reason.strip()) < 3:
        raise LifecycleError("REASON_REQUIRED", "a reason is required")
    return reason.strip()[:300]


def _close_things_tied_to_the_cell(session: Session, resident_id: int, now: datetime) -> dict:
    """Ends what only makes sense on the unit: live mirror sessions, booked visits and rec."""
    mirrors = 0
    for m in session.execute(
        select(MirrorSession).where(
            MirrorSession.resident_id == resident_id, MirrorSession.ended_at.is_(None)
        )
    ).scalars():
        m.ended_at, m.end_reason = now, "manual"
        mirrors += 1
    videos = 0
    for b in session.execute(
        select(VideoBooking).where(
            VideoBooking.resident_id == resident_id,
            VideoBooking.status == "scheduled",
            VideoBooking.starts_at > now,
        )
    ).scalars():
        b.status = "cancelled"
        videos += 1
    recs = 0
    for r in session.execute(
        select(RecBooking).where(
            RecBooking.resident_id == resident_id, RecBooking.day >= now.date()
        )
    ).scalars():
        session.delete(r)
        recs += 1
    return {"mirror_sessions_ended": mirrors, "video_cancelled": videos, "rec_cancelled": recs}


def vacate(
    session: Session, actor: Actor, resident_id: int, reason: str, now: datetime
) -> Placement:
    """The resident leaves: release, court, hospital, any reason. Frees the cell and the device."""
    resident = _resident(session, resident_id)
    why = _reason(reason)
    row = _open_assignment(session, resident_id)
    cell, device = session.get(Cell, row.cell_id), session.get(Device, row.device_id)
    row.ended_at = now
    resident.released_at = now
    closed = _close_things_tied_to_the_cell(session, resident_id, now)
    for f in session.execute(
        select(WelfareFlag).where(
            WelfareFlag.resident_id == resident_id, WelfareFlag.status == "open"
        )
    ).scalars():
        f.status, f.cleared_at = "cleared", now
    append_audit(
        session,
        actor,
        "resident_vacated",
        "resident",
        resident.code,
        reason_code="VACATE",
        payload={"reason": why, "cell": cell.code, "device": device.code, **closed},
    )
    session.flush()
    return Placement(resident.id, resident.code, cell.code, device.code)


def transfer(
    session: Session,
    actor: Actor,
    resident_id: int,
    cell_code: str,
    device_code: str,
    reason: str,
    now: datetime,
) -> dict:
    """Moves a resident to another cell (and the device on its wall). Returns the new place and
    any keep-separate residents already on the destination unit, so staff see the conflict."""
    resident = _resident(session, resident_id)
    why = _reason(reason)
    old = _open_assignment(session, resident_id)
    old_cell = session.get(Cell, old.cell_id)
    new_cell, new_device = _find_place(session, cell_code, device_code)
    old.ended_at = now
    session.add(
        DeviceAssignment(
            device_id=new_device.id,
            cell_id=new_cell.id,
            resident_id=resident.id,
            assigned_by=actor.id,
            assigned_at=now,
        )
    )
    closed = (
        _close_things_tied_to_the_cell(session, resident_id, now)
        if old_cell.unit != new_cell.unit
        else {}
    )
    conflicts = _keep_separate_on_unit(session, resident_id, new_cell.unit)
    append_audit(
        session,
        actor,
        "resident_transferred",
        "resident",
        resident.code,
        reason_code="TRANSFER",
        payload={
            "reason": why,
            "from_cell": old_cell.code,
            "to_cell": new_cell.code,
            "device": new_device.code,
            "keep_separate_on_new_unit": conflicts,
            **closed,
        },
    )
    session.flush()
    return {
        "cell": new_cell.code,
        "device": new_device.code,
        "keep_separate_on_new_unit": conflicts,
    }


def _keep_separate_on_unit(session: Session, resident_id: int, unit: str) -> list[str]:
    """Codes of residents who must be kept apart from this one and live on `unit` now."""
    pairs = session.execute(
        select(KeepSeparate.resident_a_id, KeepSeparate.resident_b_id).where(
            KeepSeparate.ended_at.is_(None),
            (KeepSeparate.resident_a_id == resident_id)
            | (KeepSeparate.resident_b_id == resident_id),
        )
    ).all()
    others = {b if a == resident_id else a for a, b in pairs}
    if not others:
        return []
    return list(
        session.execute(
            select(Resident.code)
            .join(DeviceAssignment, DeviceAssignment.resident_id == Resident.id)
            .join(Cell, Cell.id == DeviceAssignment.cell_id)
            .where(Resident.id.in_(others), DeviceAssignment.ended_at.is_(None), Cell.unit == unit)
            .order_by(Resident.code)
        ).scalars()
    )
