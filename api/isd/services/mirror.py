"""Live mirror: a logged, time-limited, read-only look at a device's current screen."""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from isd.engine.mirror import REDACTED_PATH, redaction_reason
from isd.models import CallRecord, Device, DeviceAssignment, MirrorSession, Resident
from isd.schemas import ResidentView
from isd.services.audit import Actor, append_audit
from isd.services.config_store import get_current
from isd.services.resident_view import build_resident_view

MIRROR_ROLES = ("supervisor", "admin")


class MirrorError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _limits(session: Session) -> tuple[timedelta, timedelta]:
    c = get_current(session, "compliance").payload
    return timedelta(minutes=int(c["mirror_max_minutes"])), timedelta(
        seconds=int(c["mirror_idle_seconds"])
    )


def _device_for(session: Session, resident_id: int) -> Device | None:
    return session.execute(
        select(Device)
        .join(DeviceAssignment, DeviceAssignment.device_id == Device.id)
        .where(DeviceAssignment.resident_id == resident_id, DeviceAssignment.ended_at.is_(None))
    ).scalar()


def _close(session: Session, m: MirrorSession, actor: Actor, ended: datetime, why: str) -> None:
    m.ended_at, m.end_reason = ended, why
    append_audit(
        session,
        actor,
        "mirror_ended",
        "resident",
        m.resident_id,
        reason_code={"manual": "MIRROR_END", "timeout": "MIRROR_TIMEOUT", "idle": "MIRROR_IDLE"}[
            why
        ],
        payload={
            "session_id": m.id,
            "seconds": int((ended - m.started_at).total_seconds()),
            "frames": m.frames_served,
        },
    )


def start(
    session: Session, actor: Actor, resident_id: int, reason: str, now: datetime
) -> MirrorSession:
    if actor.role not in MIRROR_ROLES:
        raise MirrorError("ROLE_NOT_PERMITTED", "only supervisors and admins can mirror a device")
    if len(reason.strip()) < 5:
        raise MirrorError("REASON_REQUIRED", "give a reason for watching this device")
    if session.get(Resident, resident_id) is None:
        raise MirrorError("NOT_FOUND", "resident not found")
    device = _device_for(session, resident_id)
    if device is None:
        raise MirrorError("NO_DEVICE", "this resident has no assigned device")
    m = MirrorSession(
        staff_id=actor.id,
        resident_id=resident_id,
        device_id=device.id,
        reason=reason.strip(),
        started_at=now,
        last_seen_at=now,
    )
    session.add(m)
    session.flush()
    append_audit(
        session,
        actor,
        "mirror_started",
        "resident",
        resident_id,
        reason_code="MIRROR_START",
        payload={"session_id": m.id, "device": device.code, "reason": m.reason},
    )
    return m


def _load(session: Session, actor: Actor, session_id: int) -> MirrorSession:
    m = session.execute(
        select(MirrorSession).where(MirrorSession.id == session_id).with_for_update()
    ).scalar()
    if m is None or (m.staff_id != actor.id and actor.role != "admin"):
        raise MirrorError("NOT_FOUND", "mirror session not found")
    return m


def frame(session: Session, actor: Actor, session_id: int, now: datetime) -> dict:
    m = _load(session, actor, session_id)
    if m.ended_at is not None:
        raise MirrorError("ENDED", "this mirror session has ended")
    max_len, idle = _limits(session)
    if now - m.started_at > max_len:
        _close(session, m, actor, m.started_at + max_len, "timeout")
        raise MirrorError("ENDED", "mirror session reached its time limit")
    if now - m.last_seen_at > idle:
        _close(session, m, actor, m.last_seen_at, "idle")
        raise MirrorError("ENDED", "mirror session closed after inactivity")
    m.last_seen_at = now
    m.frames_served += 1

    device = session.get(Device, m.device_id)
    on_private_call = (
        session.execute(
            select(CallRecord.id).where(
                CallRecord.resident_id == m.resident_id,
                CallRecord.status == "active",
                CallRecord.privileged.is_(True),
            )
        ).first()
        is not None
    )
    why = redaction_reason(device.current_screen, on_private_call)
    resident = session.get(Resident, m.resident_id)
    view: ResidentView | None = None if why else build_resident_view(session, m.resident_id, now)
    return {
        "session_id": m.id,
        "resident_code": resident.code,
        "started_at": m.started_at.isoformat(),
        "expires_at": (m.started_at + max_len).isoformat(),
        "redacted": why,
        "screen": None
        if why
        else {
            "path": device.current_screen,
            "reported_at": device.screen_at.isoformat() if device.screen_at else None,
            "age_seconds": int((now - device.screen_at).total_seconds())
            if device.screen_at
            else None,
        },
        "view": view.model_dump(mode="json") if view else None,
    }


def end(session: Session, actor: Actor, session_id: int, now: datetime) -> MirrorSession:
    m = _load(session, actor, session_id)
    if m.ended_at is None:
        _close(session, m, actor, now, "manual")
    return m


def list_sessions(session: Session, actor: Actor, limit: int = 100) -> list[dict]:
    q = select(MirrorSession).order_by(MirrorSession.id.desc()).limit(limit)
    if actor.role == "supervisor":
        q = q.where(MirrorSession.staff_id == actor.id)
    rows = session.execute(q).scalars().all()
    codes = {r.id: r.code for r in session.execute(select(Resident)).scalars()}
    from isd.models import Staff

    names = {s.id: s.username for s in session.execute(select(Staff)).scalars()}
    return [
        {
            "id": m.id,
            "staff": names.get(m.staff_id, "?"),
            "resident_code": codes.get(m.resident_id, "?"),
            "reason": m.reason,
            "started_at": m.started_at.isoformat(),
            "ended_at": m.ended_at.isoformat() if m.ended_at else None,
            "end_reason": m.end_reason,
            "seconds": int(((m.ended_at or m.last_seen_at) - m.started_at).total_seconds()),
            "frames": m.frames_served,
        }
        for m in rows
    ]


def record_screen(session: Session, device: Device, path: str, now: datetime) -> None:
    """Called by the kiosk when its route changes. Private screens are never stored."""
    from isd.engine.mirror import is_private_path

    device.current_screen = REDACTED_PATH if is_private_path(path) else path
    device.screen_at = now
