"""Health requests queue. Visible to health_staff, supervisor, admin, auditor.
Hidden from officers (invariant: sensitive medical data)."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from isd.auth import require_roles
from isd.db import get_db
from isd.models import HealthRequest, Staff
from isd.services.audit import Actor, append_audit

router = APIRouter(prefix="/staff/health-requests", tags=["staff-health"])
READ = require_roles("health_staff", "supervisor", "admin", "auditor")
WRITE = require_roles("health_staff", "supervisor", "admin")


class UpdateBody(BaseModel):
    status: str | None = None
    staff_note: str | None = None


@router.get("")
def list_requests(
    status: str | None = None,
    staff: Staff = Depends(READ),
    db: Session = Depends(get_db),
) -> list[dict]:
    q = db.query(HealthRequest)
    if status:
        q = q.filter(HealthRequest.status == status)
    return [_row(r) for r in q.order_by(HealthRequest.created_at.desc()).all()]


@router.patch("/{request_id}")
def update_request(
    request_id: int,
    body: UpdateBody,
    staff: Staff = Depends(WRITE),
    db: Session = Depends(get_db),
) -> dict:
    r = db.get(HealthRequest, request_id)
    if not r:
        raise HTTPException(404, "not found")
    if body.status is not None:
        r.status = body.status
    if body.staff_note is not None:
        r.staff_note = body.staff_note
    r.staff_id = staff.id
    r.updated_at = datetime.now(UTC)
    append_audit(
        db,
        Actor(staff.id, staff.role),
        "health_request_update",
        "health_request",
        request_id,
        payload={"status": r.status},
    )
    db.commit()
    return _row(r)


def _row(r: HealthRequest) -> dict:
    return {
        "id": r.id,
        "resident_id": r.resident_id,
        "kind": r.kind,
        "description": r.description,
        "status": r.status,
        "staff_id": r.staff_id,
        "staff_note": r.staff_note,
        "created_at": r.created_at.isoformat(),
        "updated_at": r.updated_at.isoformat(),
    }
