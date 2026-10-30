"""Attorney call requests. legal_liaison approves/schedules; supervisor+admin also.
INVARIANT 6: attorney communications are never recorded. Only call occurrence and duration."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from isd.auth import require_roles
from isd.db import get_db
from isd.models import AttorneyCallRequest, Staff
from isd.services.audit import Actor, append_audit

router = APIRouter(prefix="/staff/attorney-calls", tags=["staff-attorney"])
READ = require_roles("legal_liaison", "supervisor", "admin", "auditor")
WRITE = require_roles("legal_liaison", "supervisor", "admin")


class UpdateBody(BaseModel):
    status: str | None = None
    staff_note: str | None = None
    scheduled_at: str | None = None


@router.get("")
def list_requests(
    status: str | None = None,
    staff: Staff = Depends(READ),
    db: Session = Depends(get_db),
) -> list[dict]:
    q = db.query(AttorneyCallRequest)
    if status:
        q = q.filter(AttorneyCallRequest.status == status)
    return [_row(r) for r in q.order_by(AttorneyCallRequest.requested_at.desc()).all()]


@router.patch("/{request_id}")
def update_request(
    request_id: int,
    body: UpdateBody,
    staff: Staff = Depends(WRITE),
    db: Session = Depends(get_db),
) -> dict:
    r = db.get(AttorneyCallRequest, request_id)
    if not r:
        raise HTTPException(404, "not found")
    if body.status is not None:
        r.status = body.status
    if body.staff_note is not None:
        r.staff_note = body.staff_note
    if body.scheduled_at is not None:
        r.scheduled_at = datetime.fromisoformat(body.scheduled_at)
    r.staff_id = staff.id
    append_audit(
        db,
        Actor(staff.id, staff.role),
        "attorney_call_update",
        "attorney_call_request",
        request_id,
        payload={"status": r.status},
    )
    db.commit()
    return _row(r)


def _row(r: AttorneyCallRequest) -> dict:
    return {
        "id": r.id,
        "resident_id": r.resident_id,
        "contact_id": r.contact_id,
        "attorney_name": r.attorney_name,
        "attorney_phone": r.attorney_phone,
        "status": r.status,
        "staff_id": r.staff_id,
        "staff_note": r.staff_note,
        "requested_at": r.requested_at.isoformat(),
        "scheduled_at": r.scheduled_at.isoformat() if r.scheduled_at else None,
    }
