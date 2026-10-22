"""Staff endpoints for welfare, out-of-cell time, activity timeline, content sources and jobs."""

from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from isd.auth import require_roles
from isd.db import get_db
from isd.models import ROLES, JobEnrollment, JobListing, Resident, Staff
from isd.services import jobs, out_of_cell, reading, timeline, welfare
from isd.services.audit import Actor

router = APIRouter(prefix="/staff", tags=["staff-extras"])
ALL = require_roles(*ROLES)
FLOOR_STAFF = require_roles("officer", "supervisor", "admin")
ADMIN = require_roles("admin")


def _now() -> datetime:
    return datetime.now(UTC)


# ---------------- welfare & out-of-cell ----------------
@router.get("/welfare")
def welfare_flags(_: Staff = Depends(ALL), db: Session = Depends(get_db)) -> list[dict]:
    return welfare.all_flags(db, _now())


class AckIn(BaseModel):
    resident_id: int
    flag_type: str
    note: str


@router.post("/welfare/ack", status_code=201)
def welfare_ack(
    body: AckIn, staff: Staff = Depends(FLOOR_STAFF), db: Session = Depends(get_db)
) -> dict:
    try:
        a = welfare.acknowledge(
            db, Actor(staff.id, staff.role), body.resident_id, body.flag_type, body.note, _now()
        )
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return {"id": a.id}


class OutOfCellIn(BaseModel):
    resident_id: int
    day: date
    minutes: int = Field(ge=0, le=1440)


@router.post("/out-of-cell", status_code=201)
def record_out_of_cell(
    body: OutOfCellIn, staff: Staff = Depends(FLOOR_STAFF), db: Session = Depends(get_db)
) -> dict:
    try:
        row = out_of_cell.record(
            db,
            Actor(staff.id, staff.role),
            body.resident_id,
            body.day,
            body.minutes,
            "facility",
            _now(),
        )
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return {"id": row.id}


@router.get("/residents/{resident_id}/out-of-cell")
def resident_out_of_cell(
    resident_id: int, days: int = 14, _: Staff = Depends(ALL), db: Session = Depends(get_db)
) -> list[dict]:
    if db.get(Resident, resident_id) is None:
        raise HTTPException(404, "resident not found")
    return [
        {"day": d.isoformat(), "minutes": m}
        for d, m in out_of_cell.window(db, resident_id, _now().date(), min(max(days, 1), 60))
    ]


# ---------------- activity timeline (monitoring access is audit-logged) ----------------
@router.get("/residents/{resident_id}/timeline")
def resident_timeline(
    resident_id: int,
    reason: str,
    staff: Staff = Depends(require_roles("supervisor", "admin", "auditor")),
    db: Session = Depends(get_db),
) -> list[dict]:
    if db.get(Resident, resident_id) is None:
        raise HTTPException(404, "resident not found")
    try:
        return timeline.timeline(db, Actor(staff.id, staff.role), resident_id, reason, _now())
    except timeline.TimelineDenied as e:
        raise HTTPException(409, {"code": e.code, "message": str(e)}) from e


# ---------------- approved content sources (allow-list) ----------------
class SourceIn(BaseModel):
    name: str = Field(min_length=3, max_length=128)
    kind: str = Field(pattern="^(bundled|external)$")
    base_url: str | None = None


class ActiveIn(BaseModel):
    active: bool


@router.get("/content-sources")
def content_sources(_: Staff = Depends(ALL), db: Session = Depends(get_db)) -> list[dict]:
    return [
        {
            "id": s.id,
            "name": s.name,
            "kind": s.kind,
            "base_url": s.base_url,
            "active": s.active,
            "protected": s.protected,
        }
        for s in reading.list_sources(db)
    ]


@router.post("/content-sources", status_code=201)
def add_content_source(
    body: SourceIn, staff: Staff = Depends(ADMIN), db: Session = Depends(get_db)
) -> dict:
    try:
        row = reading.add_source(
            db, Actor(staff.id, staff.role), body.name, body.kind, body.base_url, _now()
        )
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return {"id": row.id}


@router.post("/content-sources/{source_id}/active")
def set_content_source_active(
    source_id: int, body: ActiveIn, staff: Staff = Depends(ADMIN), db: Session = Depends(get_db)
) -> dict:
    try:
        row = reading.set_source_active(db, Actor(staff.id, staff.role), source_id, body.active)
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    except ValueError as e:
        raise HTTPException(409, str(e)) from e
    return {"id": row.id, "active": row.active}


# ---------------- job listings (staff side; individual participation is not shown) ----------------
class JobIn(BaseModel):
    code: str = Field(min_length=2, max_length=32)
    title: str = Field(min_length=3, max_length=128)
    task_type: str
    description: str


@router.get("/jobs")
def job_listings(_: Staff = Depends(ALL), db: Session = Depends(get_db)) -> list[dict]:
    counts = dict(
        db.execute(
            select(JobEnrollment.listing_id, func.count())
            .where(JobEnrollment.status == "active")
            .group_by(JobEnrollment.listing_id)
        ).all()
    )
    return [
        {
            "id": j.id,
            "code": j.code,
            "title": j.title,
            "task_type": j.task_type,
            "active": j.active,
            "participants": counts.get(j.id, 0),
        }
        for j in db.execute(select(JobListing).order_by(JobListing.id)).scalars()
    ]


@router.post("/jobs", status_code=201)
def create_job(body: JobIn, staff: Staff = Depends(ADMIN), db: Session = Depends(get_db)) -> dict:
    try:
        row = jobs.create_listing(
            db,
            Actor(staff.id, staff.role),
            body.code,
            body.title,
            body.task_type,
            body.description,
            _now(),
        )
    except jobs.JobError as e:
        raise HTTPException(422, {"code": e.code, "message": str(e)}) from e
    return {"id": row.id}


@router.post("/jobs/{listing_id}/active")
def set_job_active(
    listing_id: int, body: ActiveIn, staff: Staff = Depends(ADMIN), db: Session = Depends(get_db)
) -> dict:
    try:
        row = jobs.set_active(db, Actor(staff.id, staff.role), listing_id, body.active)
    except jobs.JobError as e:
        raise HTTPException(404, str(e)) from e
    return {"id": row.id, "active": row.active}
