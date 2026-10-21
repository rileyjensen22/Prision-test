"""Sandbox ("view as resident", dry run) and live mirror endpoints for staff."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from isd.auth import require_roles
from isd.db import get_db, get_readonly_db
from isd.engine.sandbox import SandboxOverrides, SandboxSanction
from isd.models import ROLES, Staff
from isd.schemas import ResidentView
from isd.services import mirror
from isd.services.audit import Actor
from isd.services.resident_view import build_resident_view

router = APIRouter(prefix="/staff", tags=["view-as"])


class SandboxSanctionIn(BaseModel):
    code: str
    hours_remaining: float | None = None


class OverridesIn(BaseModel):
    tier: int | None = None
    prior_returns: int | None = None
    offense_categories: list[str] | None = None
    add_sanctions: list[SandboxSanctionIn] = []
    clear_sanctions: bool = False
    language: str | None = Field(default=None, pattern="^(en|es)$")
    text_size: str | None = Field(default=None, pattern="^(normal|large|xlarge)$")
    reading_level: str | None = Field(default=None, pattern="^(simple|standard)$")
    captions: bool | None = None


class SandboxIn(BaseModel):
    resident_id: int
    at_time: datetime | None = None
    overrides: OverridesIn = OverridesIn()


@router.post("/sandbox/view", response_model=ResidentView)
def sandbox_view(
    body: SandboxIn,
    _: Staff = Depends(require_roles(*ROLES)),
    db: Session = Depends(get_readonly_db),
):
    """A read-only dry run. The database transaction is READ ONLY, so nothing here can write."""
    now = datetime.now(UTC)
    at = body.at_time or now
    if at.tzinfo is None:
        at = at.replace(tzinfo=UTC)
    if not now - timedelta(days=3 * 365) <= at <= now + timedelta(days=366):
        raise HTTPException(422, "time travel is limited to 3 years back and 1 year ahead")
    o = body.overrides
    overrides = SandboxOverrides(
        tier=o.tier,
        prior_returns=o.prior_returns,
        offense_categories=tuple(o.offense_categories)
        if o.offense_categories is not None
        else None,
        add_sanctions=tuple(SandboxSanction(s.code, s.hours_remaining) for s in o.add_sanctions),
        clear_sanctions=o.clear_sanctions,
        language=o.language,
        text_size=o.text_size,
        reading_level=o.reading_level,
        captions=o.captions,
    )
    try:
        return build_resident_view(db, body.resident_id, at, simulation=True, overrides=overrides)
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


# ---------------- live mirror ----------------
def _err(e: mirror.MirrorError) -> HTTPException:
    status = {"ROLE_NOT_PERMITTED": 403, "NOT_FOUND": 404, "ENDED": 410}.get(e.code, 409)
    return HTTPException(status, {"code": e.code, "message": str(e)})


class MirrorStartIn(BaseModel):
    resident_id: int
    reason: str


MIRROR_STAFF = require_roles("supervisor", "admin")


@router.post("/mirror/sessions", status_code=201)
def start_mirror(
    body: MirrorStartIn, staff: Staff = Depends(MIRROR_STAFF), db: Session = Depends(get_db)
) -> dict:
    try:
        m = mirror.start(
            db, Actor(staff.id, staff.role), body.resident_id, body.reason, datetime.now(UTC)
        )
    except mirror.MirrorError as e:
        raise _err(e) from e
    return {"session_id": m.id}


@router.get("/mirror/sessions/{session_id}/frame")
def mirror_frame(
    session_id: int, staff: Staff = Depends(MIRROR_STAFF), db: Session = Depends(get_db)
):
    try:
        return mirror.frame(db, Actor(staff.id, staff.role), session_id, datetime.now(UTC))
    except mirror.MirrorError as e:
        db.commit()  # keep the audit entry written when a session times out
        raise _err(e) from e


@router.post("/mirror/sessions/{session_id}/end")
def end_mirror(
    session_id: int, staff: Staff = Depends(MIRROR_STAFF), db: Session = Depends(get_db)
) -> dict:
    try:
        m = mirror.end(db, Actor(staff.id, staff.role), session_id, datetime.now(UTC))
    except mirror.MirrorError as e:
        raise _err(e) from e
    return {"session_id": m.id, "ended": m.ended_at is not None, "end_reason": m.end_reason}


@router.get("/mirror/sessions")
def mirror_history(
    staff: Staff = Depends(require_roles("supervisor", "admin", "auditor")),
    db: Session = Depends(get_db),
) -> list[dict]:
    return mirror.list_sessions(db, Actor(staff.id, staff.role))
