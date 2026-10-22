"""Staff endpoints for the unit schedule and for logging who is out of the cell."""

from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from isd.auth import require_roles
from isd.db import get_db
from isd.models import ROLES, Staff
from isd.services import movement, schedule
from isd.services.audit import Actor

router = APIRouter(prefix="/staff", tags=["staff-floor"])
ALL = require_roles(*ROLES)
FLOOR_STAFF = require_roles("officer", "supervisor", "admin")
SUPERVISORS = require_roles("supervisor", "admin")
EXPORTERS = require_roles("supervisor", "admin", "auditor")
ADMIN = require_roles("admin")


def _now() -> datetime:
    return datetime.now(UTC)


def _fail(e: Exception) -> HTTPException:
    code = getattr(e, "code", "ERROR")
    return HTTPException(404 if code == "NOT_FOUND" else 409, {"code": code, "message": str(e)})


# ---------------- schedule ----------------
@router.get("/schedule/units")
def schedule_units(_: Staff = Depends(ALL), db: Session = Depends(get_db)) -> list[str]:
    return schedule.units(db)


@router.get("/schedule")
def schedule_day(
    unit: str, day: date, _: Staff = Depends(ALL), db: Session = Depends(get_db)
) -> dict:
    return schedule.admin_view(db, unit, day)


class BlockIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    unit: str = Field(min_length=1, max_length=16)
    day: date
    kind: str = Field(max_length=8)
    start: str = Field(min_length=5, max_length=5)
    minutes: int = Field(ge=1, le=600)
    capacity: int = Field(ge=1, le=200)
    title: str | None = Field(default=None, max_length=128)
    required_feature: str | None = Field(default=None, max_length=32)
    reason: str = Field(max_length=500)


@router.post("/schedule/blocks", status_code=201)
def add_block(
    body: BlockIn, staff: Staff = Depends(SUPERVISORS), db: Session = Depends(get_db)
) -> dict:
    try:
        b = schedule.add_block(
            db,
            Actor(staff.id, staff.role),
            body.unit,
            body.day,
            body.kind,
            body.start,
            body.minutes,
            body.capacity,
            body.title,
            body.required_feature,
            body.reason,
            _now(),
        )
    except schedule.ScheduleError as e:
        raise _fail(e) from e
    return {"id": b.id}


class CancelIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(max_length=500)


@router.post("/schedule/blocks/{block_id}/cancel")
def cancel_block(
    block_id: int,
    body: CancelIn,
    staff: Staff = Depends(SUPERVISORS),
    db: Session = Depends(get_db),
) -> dict:
    try:
        b = schedule.cancel_block(db, Actor(staff.id, staff.role), block_id, body.reason, _now())
    except schedule.ScheduleError as e:
        raise _fail(e) from e
    return {"id": b.id, "status": b.status}


@router.post("/schedule/generate")
def generate_schedule(
    days: int = 7, _: Staff = Depends(ADMIN), db: Session = Depends(get_db)
) -> dict:
    return {"blocks_made": schedule.generate(db, _now(), max(1, min(days, 31)))}


# ---------------- movement ----------------
class MoveOutIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resident_ids: list[int] = Field(min_length=1, max_length=movement.MAX_BULK)
    activity: str = Field(max_length=8)
    block_id: int | None = None


class MoveInIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resident_ids: list[int] = Field(min_length=1, max_length=movement.MAX_BULK)


@router.post("/movement/out")
def move_out(
    body: MoveOutIn, staff: Staff = Depends(FLOOR_STAFF), db: Session = Depends(get_db)
) -> list[dict]:
    try:
        return movement.bulk_out(
            db,
            Actor(staff.id, staff.role),
            body.resident_ids,
            body.activity,
            _now(),
            body.block_id,
        )
    except movement.MovementError as e:
        raise _fail(e) from e


@router.post("/movement/in")
def move_in(
    body: MoveInIn, staff: Staff = Depends(FLOOR_STAFF), db: Session = Depends(get_db)
) -> list[dict]:
    try:
        return movement.bulk_in(db, Actor(staff.id, staff.role), body.resident_ids, _now())
    except movement.MovementError as e:
        raise _fail(e) from e


@router.get("/movement/now")
def out_now(
    unit: str | None = None, _: Staff = Depends(ALL), db: Session = Depends(get_db)
) -> list[dict]:
    """Who is out of the cell right now."""
    return movement.who_is_out(db, _now(), unit)


@router.get("/movement/discrepancies")
def discrepancy_report(
    day: date, unit: str | None = None, _: Staff = Depends(ALL), db: Session = Depends(get_db)
) -> dict:
    return movement.discrepancies(db, day, _now(), unit)


@router.get("/movement/export")
def export_day(
    day: date,
    unit: str | None = None,
    format: str = "csv",
    staff: Staff = Depends(EXPORTERS),
    db: Session = Depends(get_db),
) -> Response:
    if format not in ("csv", "json"):
        raise HTTPException(422, "format must be csv or json")
    body, media = movement.export_day(db, Actor(staff.id, staff.role), day, _now(), unit, format)
    return Response(
        body,
        media_type=media,
        headers={
            "Content-Disposition": f'attachment; filename="out-of-cell-{day.isoformat()}.{format}"'
        },
    )
