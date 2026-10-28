"""Staff endpoints for contact approvals and monitored-message review."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from isd.auth import require_roles
from isd.db import get_db
from isd.models import Staff
from isd.services import contacts, monitoring
from isd.services.audit import Actor

router = APIRouter(prefix="/staff", tags=["staff-comms"])
FLOOR_STAFF = require_roles("officer", "supervisor", "admin")
READERS = require_roles(*monitoring.READER_ROLES)
REVIEWERS = require_roles(*monitoring.REVIEWER_ROLES)
SUPERVISORS = require_roles("supervisor", "admin")


def _now() -> datetime:
    return datetime.now(UTC)


def _status(code: str) -> int:
    return {"NOT_FOUND": 404, "FORBIDDEN": 403, "PRIVILEGED_DENIED": 403}.get(code, 409)


# ---------------- contact requests ----------------
@router.get("/contact-requests")
def pending_contacts(_: Staff = Depends(FLOOR_STAFF), db: Session = Depends(get_db)) -> list[dict]:
    return contacts.pending(db)


class ReviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approve: bool
    note: str = Field(default="", max_length=500)


@router.post("/contact-requests/{contact_id}/review")
def review_contact(
    contact_id: int,
    body: ReviewIn,
    staff: Staff = Depends(FLOOR_STAFF),
    db: Session = Depends(get_db),
) -> dict:
    try:
        c = contacts.review_contact(
            db, Actor(staff.id, staff.role), contact_id, body.approve, body.note, _now()
        )
    except contacts.ContactReviewError as e:
        raise HTTPException(_status(e.code), {"code": e.code, "message": str(e)}) from e
    return {"id": c.id, "status": c.status, "verification": c.verification}


class BlockIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    blocked: bool
    reason: str = Field(max_length=500)


@router.post("/contacts/{contact_id}/block")
def block_contact(
    contact_id: int,
    body: BlockIn,
    staff: Staff = Depends(SUPERVISORS),
    db: Session = Depends(get_db),
) -> dict:
    try:
        c = contacts.set_blocked(
            db, Actor(staff.id, staff.role), contact_id, body.blocked, body.reason, _now()
        )
    except contacts.ContactReviewError as e:
        raise HTTPException(_status(e.code), {"code": e.code, "message": str(e)}) from e
    return {"id": c.id, "blocked": c.blocked}


# ---------------- monitored messages ----------------
@router.get("/monitoring/messages")
def monitored_messages(
    flagged: bool = False, _: Staff = Depends(READERS), db: Session = Depends(get_db)
) -> list[dict]:
    """Metadata only. The text is revealed one message at a time, with a reason."""
    return monitoring.queue(db, flagged_only=flagged)


class ReadIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(max_length=500)


@router.post("/monitoring/messages/{message_id}/read")
def read_monitored_message(
    message_id: int,
    body: ReadIn,
    staff: Staff = Depends(READERS),
    db: Session = Depends(get_db),
) -> dict:
    try:
        return monitoring.read_message(
            db, Actor(staff.id, staff.role), message_id, body.reason, _now()
        )
    except monitoring.MonitoringDenied as e:
        if e.code == "PRIVILEGED_DENIED":
            db.commit()  # keep the "monitoring_denied" audit entry: get_db rolls back on errors
        raise HTTPException(_status(e.code), {"code": e.code, "message": str(e)}) from e


class FlagReviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    outcome: str = Field(max_length=16)
    reason: str = Field(max_length=500)


@router.post("/monitoring/flags/{flag_id}/review")
def review_flag(
    flag_id: int,
    body: FlagReviewIn,
    staff: Staff = Depends(REVIEWERS),
    db: Session = Depends(get_db),
) -> dict:
    try:
        f = monitoring.review_flag(
            db, Actor(staff.id, staff.role), flag_id, body.outcome, body.reason, _now()
        )
    except monitoring.MonitoringDenied as e:
        raise HTTPException(_status(e.code), {"code": e.code, "message": str(e)}) from e
    return {"id": f.id, "status": f.status}


# ---------------- monitored phone calls ----------------
@router.get("/monitoring/calls")
def monitored_calls(_: Staff = Depends(READERS), db: Session = Depends(get_db)) -> list[dict]:
    """Metadata only. A recording is opened one call at a time, with a reason, by a supervisor
    or admin. Attorney calls never appear."""
    return monitoring.call_queue(db)


@router.post("/monitoring/calls/{call_id}/review")
def review_monitored_call(
    call_id: int,
    body: ReadIn,
    staff: Staff = Depends(REVIEWERS),
    db: Session = Depends(get_db),
) -> dict:
    try:
        return monitoring.review_call(db, Actor(staff.id, staff.role), call_id, body.reason)
    except monitoring.MonitoringDenied as e:
        if e.code == "PRIVILEGED_DENIED":
            db.commit()  # keep the "monitoring_denied" audit entry: get_db rolls back on errors
        raise HTTPException(_status(e.code), {"code": e.code, "message": str(e)}) from e
