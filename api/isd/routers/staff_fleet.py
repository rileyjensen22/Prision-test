"""Fleet view and device commands for staff (pairing, pause, lift, restart)."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from isd.auth import require_roles
from isd.db import get_db
from isd.models import Staff
from isd.services import device_fleet
from isd.services.audit import Actor

router = APIRouter(prefix="/staff/devices", tags=["fleet"])


def _now() -> datetime:
    return datetime.now(UTC)


def _fail(e: device_fleet.FleetError) -> HTTPException:
    status = {"NOT_FOUND": 404, "CODE_TAKEN": 409}.get(e.code, 422)
    return HTTPException(status, {"code": e.code, "message": str(e)})


@router.get("")
def fleet(
    staff: Staff = Depends(require_roles("officer", "supervisor", "admin", "auditor")),
    db: Session = Depends(get_db),
):
    return device_fleet.fleet(db, _now())


class CreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(max_length=32)


@router.post("", status_code=201)
def create(
    body: CreateIn, staff: Staff = Depends(require_roles("admin")), db: Session = Depends(get_db)
):
    try:
        device = device_fleet.create_device(db, Actor(staff.id, staff.role), body.code, _now())
    except device_fleet.FleetError as e:
        raise _fail(e) from e
    return {"device": device.code}


@router.post("/{device_code}/pairing", status_code=201)
def pairing(
    device_code: str,
    staff: Staff = Depends(require_roles("supervisor", "admin")),
    db: Session = Depends(get_db),
):
    try:
        out = device_fleet.issue_pairing(db, Actor(staff.id, staff.role), device_code, _now())
    except device_fleet.FleetError as e:
        raise _fail(e) from e
    return {**out, "expires_at": out["expires_at"].isoformat()}


class LockIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hours: float
    reason: str = Field(max_length=200)


class ReasonIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(max_length=200)


@router.post("/{device_code}/lock", status_code=201)
def lock(
    device_code: str,
    body: LockIn,
    staff: Staff = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    try:
        cmd = device_fleet.lock(
            db, Actor(staff.id, staff.role), device_code, body.hours, body.reason, _now()
        )
    except device_fleet.FleetError as e:
        raise _fail(e) from e
    return {"id": cmd.id, "ends_at": cmd.ends_at.isoformat()}


@router.post("/{device_code}/unlock", status_code=201)
def unlock(
    device_code: str,
    body: ReasonIn,
    staff: Staff = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    try:
        cmd = device_fleet.unlock(db, Actor(staff.id, staff.role), device_code, body.reason, _now())
    except device_fleet.FleetError as e:
        raise _fail(e) from e
    return {"id": cmd.id}


@router.post("/{device_code}/restart", status_code=201)
def restart(
    device_code: str,
    body: ReasonIn,
    staff: Staff = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    try:
        cmd = device_fleet.restart(
            db, Actor(staff.id, staff.role), device_code, body.reason, _now()
        )
    except device_fleet.FleetError as e:
        raise _fail(e) from e
    return {"id": cmd.id}
