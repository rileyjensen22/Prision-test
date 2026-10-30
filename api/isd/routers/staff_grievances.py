"""Grievances queue. supervisor + admin only (no dedicated coordinator — user decision)."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from isd.auth import require_roles
from isd.db import get_db
from isd.models import Grievance, Staff
from isd.services.audit import Actor, append_audit

router = APIRouter(prefix="/staff/grievances", tags=["staff-grievances"])
READ = require_roles("supervisor", "admin", "auditor")
WRITE = require_roles("supervisor", "admin")


class UpdateBody(BaseModel):
    status: str | None = None
    response: str | None = None
    assigned_to: int | None = None


@router.get("")
def list_grievances(
    status: str | None = None,
    staff: Staff = Depends(READ),
    db: Session = Depends(get_db),
) -> list[dict]:
    q = db.query(Grievance)
    if status:
        q = q.filter(Grievance.status == status)
    return [_row(g) for g in q.order_by(Grievance.created_at.desc()).all()]


@router.patch("/{grievance_id}")
def update_grievance(
    grievance_id: int,
    body: UpdateBody,
    staff: Staff = Depends(WRITE),
    db: Session = Depends(get_db),
) -> dict:
    g = db.get(Grievance, grievance_id)
    if not g:
        raise HTTPException(404, "not found")
    if body.status is not None:
        g.status = body.status
    if body.response is not None:
        g.response = body.response
    if body.assigned_to is not None:
        g.assigned_to = body.assigned_to
    g.updated_at = datetime.now(UTC)
    append_audit(
        db,
        Actor(staff.id, staff.role),
        "grievance_update",
        "grievance",
        grievance_id,
        payload={"status": g.status},
    )
    db.commit()
    return _row(g)


def _row(g: Grievance) -> dict:
    return {
        "id": g.id,
        "resident_id": g.resident_id,
        "category": g.category,
        "description": g.description,
        "status": g.status,
        "assigned_to": g.assigned_to,
        "response": g.response,
        "due_at": g.due_at.isoformat() if g.due_at else None,
        "created_at": g.created_at.isoformat(),
        "updated_at": g.updated_at.isoformat(),
    }
