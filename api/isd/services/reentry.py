"""Release date, reentry checklist and the approved resources directory."""

from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from isd.engine.reentry import CHECKLIST_STATUSES, checklist_progress, countdown, latest_statuses
from isd.models import ReentryEvent, Resident
from isd.services import education
from isd.services.audit import Actor, append_audit
from isd.services.config_store import get_current


class ReentryError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _config(session: Session) -> dict:
    return get_current(session, "reentry").payload


def _resident(session: Session, resident_id: int) -> Resident:
    resident = session.get(Resident, resident_id)
    if resident is None:
        raise ReentryError("NOT_FOUND", "resident not found")
    return resident


def release_countdown(session: Session, resident_id: int, today: date) -> dict | None:
    resident = session.get(Resident, resident_id)
    return countdown(resident.release_date if resident else None, today)


def statuses(session: Session, resident_id: int) -> dict[str, str]:
    rows = session.execute(
        select(ReentryEvent.item_code, ReentryEvent.status)
        .where(ReentryEvent.resident_id == resident_id)
        .order_by(ReentryEvent.id)
    ).all()
    return latest_statuses([(c, s) for c, s in rows], _config(session)["checklist"])


def set_release_date(
    session: Session,
    actor: Actor,
    resident_id: int,
    release: date | None,
    reason: str,
    now: datetime,
) -> None:
    resident = _resident(session, resident_id)
    if len(reason.strip()) < 3:
        raise ReentryError("REASON_REQUIRED", "a reason is required")
    if release is not None and release < now.date():
        raise ReentryError("BAD_RELEASE_DATE", "the release date is in the past")
    before = resident.release_date
    resident.release_date = release
    append_audit(
        session,
        actor,
        "release_date_set",
        "resident",
        resident.code,
        reason_code="RELEASE_DATE",
        payload={
            "from": before.isoformat() if before else None,
            "to": release.isoformat() if release else None,
            "reason": reason.strip(),
        },
    )


def record_item(
    session: Session,
    actor: Actor,
    resident_id: int,
    item_code: str,
    status: str,
    note: str | None,
    now: datetime,
) -> ReentryEvent:
    resident = _resident(session, resident_id)
    if item_code not in {i["code"] for i in _config(session)["checklist"]}:
        raise ReentryError("UNKNOWN_ITEM", "that checklist item does not exist")
    if status not in CHECKLIST_STATUSES:
        raise ReentryError("BAD_STATUS", f"status must be one of {', '.join(CHECKLIST_STATUSES)}")
    event = ReentryEvent(
        resident_id=resident_id,
        item_code=item_code,
        status=status,
        note=(note or "").strip()[:500] or None,
        staff_id=actor.id,
        at=now,
    )
    session.add(event)
    session.flush()
    append_audit(
        session,
        actor,
        "reentry_item_recorded",
        "resident",
        resident.code,
        reason_code="REENTRY_ITEM",
        payload={"item": item_code, "status": status},  # the note stays out of the log
    )
    return event


def resident_view(session: Session, resident_id: int, now: datetime) -> dict:
    """What the device shows: countdown, checklist, reentry courses and the resources directory."""
    cfg = _config(session)
    current = statuses(session, resident_id)
    wanted = set(cfg["courses"])
    courses = [
        {
            k: c[k]
            for k in ("code", "level", "title", "lessons", "lessons_done", "completed", "allowed")
        }
        for c in education.list_courses(session, resident_id, now)
        if c["code"] in wanted
    ]
    return {
        "countdown": release_countdown(session, resident_id, now.date()),
        "checklist": [
            {
                "code": i["code"],
                "title": i["title"],
                "detail": i["detail"],
                "status": current[i["code"]],
            }
            for i in cfg["checklist"]
        ],
        "progress": checklist_progress(current),
        "courses": courses,
        "resources": cfg["resources"],
    }


def staff_view(session: Session, resident_id: int) -> dict:
    resident = _resident(session, resident_id)
    cfg = _config(session)
    current = statuses(session, resident_id)
    notes = {}
    for row in session.execute(
        select(ReentryEvent)
        .where(ReentryEvent.resident_id == resident_id)
        .order_by(ReentryEvent.id)
    ).scalars():
        notes[row.item_code] = {"note": row.note, "at": row.at.isoformat()}
    return {
        "release_date": resident.release_date.isoformat() if resident.release_date else None,
        "checklist": [
            {
                "code": i["code"],
                "title": i["title"]["en"],
                "status": current[i["code"]],
                **notes.get(i["code"], {}),
            }
            for i in cfg["checklist"]
        ],
        "progress": checklist_progress(current),
    }
