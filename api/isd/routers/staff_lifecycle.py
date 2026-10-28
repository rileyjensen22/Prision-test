"""Vacate, transfer and keep-separate screens (staff). Supervisors and admins act; auditors read."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from isd.auth import require_roles
from isd.db import get_db
from isd.models import Staff
from isd.services import intake as intake_service
from isd.services import keep_separate, lifecycle
from isd.services.audit import Actor

router = APIRouter(prefix="/staff", tags=["lifecycle"])


def _now() -> datetime:
    return datetime.now(UTC)


def _fail(e: Exception) -> HTTPException:
    code = getattr(e, "code", "ERROR")
    status = (
        404
        if code == "NOT_FOUND"
        else 409
        if code in {"OCCUPIED", "ALREADY_ENTERED", "ALREADY_ENDED", "NOT_ASSIGNED"}
        else 422
    )
    return HTTPException(status, {"code": code, "message": str(e)})


class VacateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(max_length=300)


class TransferIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cell_code: str
    device_code: str
    reason: str = Field(max_length=300)


@router.post("/residents/{resident_id}/vacate")
def vacate(
    resident_id: int,
    body: VacateIn,
    staff: Staff = Depends(require_roles("supervisor", "admin")),
    db: Session = Depends(get_db),
):
    try:
        p = lifecycle.vacate(db, Actor(staff.id, staff.role), resident_id, body.reason, _now())
    except lifecycle.LifecycleError as e:
        raise _fail(e) from e
    return {"resident": p.resident_code, "freed_cell": p.cell_code, "freed_device": p.device_code}


@router.post("/residents/{resident_id}/transfer")
def transfer(
    resident_id: int,
    body: TransferIn,
    staff: Staff = Depends(require_roles("supervisor", "admin")),
    db: Session = Depends(get_db),
):
    try:
        return lifecycle.transfer(
            db,
            Actor(staff.id, staff.role),
            resident_id,
            body.cell_code,
            body.device_code,
            body.reason,
            _now(),
        )
    except lifecycle.LifecycleError as e:
        raise _fail(e) from e
    except intake_service.IntakeError as e:
        raise _fail(e) from e


class SeparateAddIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resident_code: str
    other_code: str
    reason: str = Field(max_length=200)


class SeparateEndIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(max_length=200)


@router.get("/keep-separate")
def list_keep_separate(
    include_ended: bool = False,
    staff: Staff = Depends(require_roles("supervisor", "admin", "auditor")),
    db: Session = Depends(get_db),
):
    return keep_separate.list_open(db, include_ended)


@router.post("/keep-separate", status_code=201)
def add_keep_separate(
    body: SeparateAddIn,
    staff: Staff = Depends(require_roles("supervisor", "admin")),
    db: Session = Depends(get_db),
):
    try:
        row = keep_separate.add(
            db,
            Actor(staff.id, staff.role),
            body.resident_code,
            body.other_code,
            body.reason,
            _now(),
        )
    except keep_separate.SeparateError as e:
        raise _fail(e) from e
    return {"id": row.id}


@router.post("/keep-separate/{entry_id}/end")
def end_keep_separate(
    entry_id: int,
    body: SeparateEndIn,
    staff: Staff = Depends(require_roles("supervisor", "admin")),
    db: Session = Depends(get_db),
):
    try:
        keep_separate.end(db, Actor(staff.id, staff.role), entry_id, body.reason, _now())
    except keep_separate.SeparateError as e:
        raise _fail(e) from e
    return {"ended": entry_id}
