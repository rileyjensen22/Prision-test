"""Staff dashboard API: roster, sanction workflow, confirmations, appeals, outliers, events."""

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from isd.auth import require_roles
from isd.db import get_db
from isd.engine.authority import AuthorityError, Evidence
from isd.engine.ceiling import ceiling_tier, raw_loss
from isd.models import ROLES, Staff
from isd.services import sanctions, staff_views
from isd.services.audit import Actor
from isd.services.entitlement_service import load_engine_config

router = APIRouter(prefix="/staff", tags=["staff-ops"])
ALL = require_roles(*ROLES)
SUPERVISION = require_roles("supervisor", "admin", "auditor")


def _now() -> datetime:
    return datetime.now(UTC)


def _authority(e: AuthorityError) -> HTTPException:
    status = 403 if e.code in ("ROLE_NOT_PERMITTED",) else 409
    return HTTPException(status, {"code": e.code, "message": str(e)})


@router.get("/summary")
def summary(staff: Staff = Depends(ALL), db: Session = Depends(get_db)) -> dict:
    return staff_views.summary(db, staff.id, staff.role, _now())


@router.get("/roster")
def roster(_: Staff = Depends(ALL), db: Session = Depends(get_db)) -> list[dict]:
    return staff_views.roster(db, _now())


@router.get("/roster/page")
def roster_page(
    hub: str | None = None,
    line: str | None = None,
    floor: int | None = None,
    q: str | None = None,
    limit: int = 100,
    offset: int = 0,
    _: Staff = Depends(ALL),
    db: Session = Depends(get_db),
) -> dict:
    """The roster one page at a time, for a hub, line or floor, or a search on code or cell."""
    return staff_views.roster_page(
        db,
        _now(),
        hub=hub,
        line=line,
        floor=floor,
        q=q,
        limit=min(max(limit, 1), 500),
        offset=max(offset, 0),
    )


@router.get("/residents/lookup")
def residents_lookup(
    q: str | None = None,
    unit: str | None = None,
    line: str | None = None,
    floor: int | None = None,
    limit: int = 50,
    _: Staff = Depends(ALL),
    db: Session = Depends(get_db),
) -> list[dict]:
    """A light picker list (code, name, cell, unit, floor): no entitlements are worked out."""
    return staff_views.lookup(
        db, q=q, unit=unit, line=line, floor=floor, limit=min(max(limit, 1), 500)
    )


@router.get("/facility/overview")
def facility_overview(_: Staff = Depends(ALL), db: Session = Depends(get_db)) -> dict:
    """Cells, residents, offline devices and locked residents by hub, line and floor."""
    return staff_views.facility_overview(db, _now())


@router.get("/residents/{resident_id}")
def resident(resident_id: int, _: Staff = Depends(ALL), db: Session = Depends(get_db)) -> dict:
    detail = staff_views.resident_detail(db, resident_id, _now())
    if detail is None:
        raise HTTPException(404, "resident not found")
    return detail


@router.get("/colleagues")
def colleagues(_: Staff = Depends(ALL), db: Session = Depends(get_db)) -> list[dict]:
    return staff_views.colleagues(db)


@router.get("/infractions")
def infractions(_: Staff = Depends(ALL), db: Session = Depends(get_db)) -> list[dict]:
    cfg = load_engine_config(db)
    return [
        {
            "code": r.code,
            "label": r.label,
            "scope": r.scope,
            "duration_hours": r.duration_hours,
            "confirmation": r.confirmation,
            "severity": r.severity,
        }
        for r in cfg.infractions.values()
    ]


class EvidenceIn(BaseModel):
    type: Literal["system_event", "second_staff_report"]
    reporter_id: int | None = None
    ref: str | None = None


class SanctionIn(BaseModel):
    resident_id: int
    infraction_code: str
    evidence: EvidenceIn | None = None


@router.post("/sanctions", status_code=201)
def issue(
    body: SanctionIn,
    staff: Staff = Depends(require_roles("officer", "supervisor")),
    db: Session = Depends(get_db),
) -> dict:
    if body.evidence and body.evidence.type == "system_event":
        # Only the system (facility ingest, device tamper) can report a system-detected event.
        raise HTTPException(
            422, {"code": "EVIDENCE_REQUIRED", "message": "staff cannot file a system event"}
        )
    ev = Evidence(**body.evidence.model_dump()) if body.evidence else None
    try:
        s = sanctions.issue_sanction(
            db, Actor(staff.id, staff.role), body.resident_id, body.infraction_code, _now(), ev
        )
    except AuthorityError as e:
        raise _authority(e) from e
    return {"id": s.id, "status": s.status}


@router.get("/confirmations")
def confirmations(staff: Staff = Depends(SUPERVISION), db: Session = Depends(get_db)) -> list[dict]:
    return staff_views.confirmation_queue(db, staff.id, staff.role)


@router.post("/sanctions/{sanction_id}/confirm")
def confirm(
    sanction_id: int,
    staff: Staff = Depends(require_roles("supervisor")),
    db: Session = Depends(get_db),
) -> dict:
    try:
        s = sanctions.confirm_sanction(db, Actor(staff.id, staff.role), sanction_id, _now())
    except AuthorityError as e:
        raise _authority(e) from e
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    return {"id": s.id, "status": s.status}


class NoteIn(BaseModel):
    note: str


@router.post("/sanctions/{sanction_id}/reject")
def reject(
    sanction_id: int,
    body: NoteIn,
    staff: Staff = Depends(require_roles("supervisor")),
    db: Session = Depends(get_db),
) -> dict:
    if not body.note.strip():
        raise HTTPException(422, "a note is required")
    try:
        s = sanctions.reject_sanction(
            db, Actor(staff.id, staff.role), sanction_id, body.note, _now()
        )
    except AuthorityError as e:
        raise _authority(e) from e
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    return {"id": s.id, "status": s.status}


@router.get("/appeals")
def appeals(
    include_closed: bool = False,
    staff: Staff = Depends(SUPERVISION),
    db: Session = Depends(get_db),
) -> list[dict]:
    return staff_views.appeals_queue(db, staff.id, staff.role, _now(), include_closed)


class ReviewIn(BaseModel):
    outcome: Literal["upheld", "overturned"]
    note: str


@router.post("/appeals/{appeal_id}/review")
def review(
    appeal_id: int,
    body: ReviewIn,
    staff: Staff = Depends(require_roles("supervisor")),
    db: Session = Depends(get_db),
) -> dict:
    if not body.note.strip():
        raise HTTPException(422, "a note is required")
    try:
        a = sanctions.review_appeal(
            db, Actor(staff.id, staff.role), appeal_id, body.outcome, body.note, _now()
        )
    except AuthorityError as e:
        raise _authority(e) from e
    return {"id": a.id, "status": a.status}


@router.get("/outliers")
def outliers(_: Staff = Depends(SUPERVISION), db: Session = Depends(get_db)) -> dict:
    return staff_views.outliers(db, _now())


@router.get("/events")
def events(limit: int = 40, _: Staff = Depends(ALL), db: Session = Depends(get_db)) -> list[dict]:
    return staff_views.events(db, limit)


@router.get("/ceiling-preview")
def ceiling_preview(N: float = 12, p: float = 1.5, _: Staff = Depends(ALL)) -> list[dict]:
    """What the repeat-return curve gives for N and p, so the config editor can show a preview."""
    if not (1 <= N <= 100 and 0.5 <= p <= 5):
        raise HTTPException(422, "N must be 1..100 and p 0.5..5")
    return [
        {
            "returns": n,
            "ceiling_tier": ceiling_tier(n, N, p),
            "raw_loss": round(raw_loss(n, N, p), 2),
        }
        for n in range(0, int(N) + 2)
    ]
