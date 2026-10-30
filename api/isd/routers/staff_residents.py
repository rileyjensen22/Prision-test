"""Staff-controlled resident settings and device assignments. Residents have no route to these."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from isd.auth import require_roles
from isd.db import get_db
from isd.models import Device, DeviceAssignment, Resident, Staff
from isd.services.audit import Actor, append_audit
from isd.services import points as points_svc

router = APIRouter(prefix="/staff", tags=["staff"])


class SettingsIn(BaseModel):
    language: str | None = Field(default=None, pattern="^(en|es)$")
    text_size: str | None = Field(default=None, pattern="^(normal|large|xlarge)$")
    reading_level: str | None = Field(default=None, pattern="^(simple|standard)$")
    captions: bool | None = None
    reason: str = Field(min_length=3)


@router.put("/residents/{resident_id}/settings")
def update_settings(
    resident_id: int,
    body: SettingsIn,
    staff: Staff = Depends(require_roles("officer", "supervisor", "admin")),
    db: Session = Depends(get_db),
) -> dict:
    r = db.get(Resident, resident_id)
    if r is None:
        raise HTTPException(404, "resident not found")
    changes = {}
    for field in ("language", "text_size", "reading_level", "captions"):
        new = getattr(body, field)
        if new is not None and new != getattr(r, field):
            changes[field] = {"from": getattr(r, field), "to": new}
            setattr(r, field, new)
    if changes:
        append_audit(
            db,
            Actor(staff.id, staff.role),
            "resident_settings_change",
            "resident",
            r.code,
            reason_code="SETTINGS_EDIT",
            payload={"changes": changes, "reason": body.reason},
        )
    return {"changed": sorted(changes)}


class PointsIn(BaseModel):
    kind: str = Field(pattern="^staff_commendation$")
    reason: str = Field(min_length=5)


@router.post("/residents/{resident_id}/points", status_code=201)
def add_commendation(
    resident_id: int,
    body: PointsIn,
    staff: Staff = Depends(require_roles("officer", "supervisor", "admin")),
    db: Session = Depends(get_db),
) -> dict:
    r = db.get(Resident, resident_id)
    if r is None:
        raise HTTPException(404, "resident not found")
    now = datetime.now(UTC)
    actor = Actor(staff.id, staff.role)
    try:
        ev = points_svc.add_point_event(db, actor, resident_id, "staff_commendation", now, reason=body.reason)
    except (ValueError, PermissionError) as exc:
        raise HTTPException(422, str(exc)) from exc
    from isd.services.points import load_engine_config
    from sqlalchemy import func
    from isd.models import PointEvent as PE
    from datetime import timedelta
    cfg = points_svc.load_engine_config(db)
    rule = cfg.point_events.get("staff_commendation", {})
    weekly_max = rule.get("max_per_week", 3)
    used = db.execute(
        select(func.count()).where(
            PE.resident_id == resident_id,
            PE.kind == "staff_commendation",
            PE.created_at > now - timedelta(days=7),
        )
    ).scalar() or 0
    return {"points": ev.points, "event_id": ev.id, "weekly_remaining": max(0, weekly_max - used)}


class TierOverrideIn(BaseModel):
    max_tier_override: int = Field(ge=1, le=10)
    reason: str = Field(min_length=5)


@router.put("/residents/{resident_id}")
def update_resident(
    resident_id: int,
    body: TierOverrideIn,
    staff: Staff = Depends(require_roles("supervisor", "admin")),
    db: Session = Depends(get_db),
) -> dict:
    r = db.get(Resident, resident_id)
    if r is None:
        raise HTTPException(404, "resident not found")
    old = r.max_tier_override
    r.max_tier_override = body.max_tier_override
    append_audit(
        db,
        Actor(staff.id, staff.role),
        "tier_override",
        "resident",
        r.code,
        reason_code="TIER_OVERRIDE",
        payload={"from": old, "to": body.max_tier_override, "reason": body.reason},
    )
    return {"resident_id": resident_id, "max_tier_override": body.max_tier_override}


class AssignmentIn(BaseModel):
    device_code: str
    resident_id: int
    reason: str = Field(min_length=3)


@router.post("/device-assignments", status_code=201)
def assign_device(
    body: AssignmentIn,
    staff: Staff = Depends(require_roles("supervisor", "admin")),
    db: Session = Depends(get_db),
) -> dict:
    """Ends the device's current assignment and starts a new one (history is kept)."""
    device = db.execute(select(Device).where(Device.code == body.device_code)).scalar()
    resident = db.get(Resident, body.resident_id)
    if device is None or resident is None:
        raise HTTPException(404, "device or resident not found")
    now = datetime.now(UTC)
    current = db.execute(
        select(DeviceAssignment).where(
            DeviceAssignment.device_id == device.id, DeviceAssignment.ended_at.is_(None)
        )
    ).scalar()
    cell_id = current.cell_id if current else None
    if cell_id is None:
        raise HTTPException(409, "device has no cell; assign it to a cell first")
    if current:
        current.ended_at = now
    db.add(
        DeviceAssignment(
            device_id=device.id,
            cell_id=cell_id,
            resident_id=resident.id,
            assigned_by=staff.id,
            assigned_at=now,
        )
    )
    append_audit(
        db,
        Actor(staff.id, staff.role),
        "device_assignment",
        "device",
        device.code,
        reason_code="ASSIGNMENT_CHANGE",
        payload={
            "from_resident": current.resident_id if current else None,
            "to_resident": resident.id,
            "reason": body.reason,
        },
    )
    return {"device": device.code, "resident_id": resident.id}


@router.post("/devices/{device_code}/token")
def rotate_device_token(
    device_code: str,
    staff: Staff = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
) -> dict:
    """Issue a fresh token for a kiosk. It is shown once; give it to the device as `#device=...`."""
    from isd.services import devices

    try:
        token = devices.rotate_token(
            db, Actor(staff.id, staff.role), device_code, datetime.now(UTC)
        )
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    return {"device": device_code, "token": token, "kiosk_address_fragment": f"#device={token}"}
