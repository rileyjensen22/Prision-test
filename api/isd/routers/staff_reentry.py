"""Reentry resources — staff-editable list shown to residents approaching release."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from isd.auth import require_roles
from isd.db import get_db
from isd.models import ReentryResource, Staff
from isd.services.audit import Actor, append_audit

router = APIRouter(prefix="/staff/reentry-resources", tags=["staff-reentry"])
READ = require_roles("officer", "supervisor", "admin", "auditor", "legal_liaison")
WRITE = require_roles("supervisor", "admin", "legal_liaison")


class CreateBody(BaseModel):
    title: str
    description: str = ""
    phone: str = ""
    address: str = ""
    category: str = "general"


class UpdateBody(BaseModel):
    title: str | None = None
    description: str | None = None
    phone: str | None = None
    address: str | None = None
    category: str | None = None
    enabled: bool | None = None


@router.get("")
def list_resources(
    staff: Staff = Depends(READ),
    db: Session = Depends(get_db),
) -> list[dict]:
    return [_row(r) for r in db.query(ReentryResource).order_by(ReentryResource.title).all()]


@router.post("")
def create_resource(
    body: CreateBody,
    staff: Staff = Depends(WRITE),
    db: Session = Depends(get_db),
) -> dict:
    r = ReentryResource(
        title=body.title,
        description=body.description,
        phone=body.phone,
        address=body.address,
        category=body.category,
    )
    db.add(r)
    db.flush()
    append_audit(
        db,
        Actor(staff.id, staff.role),
        "reentry_resource_created",
        "reentry_resource",
        r.id,
        payload={"title": r.title},
    )
    db.commit()
    return _row(r)


@router.patch("/{resource_id}")
def update_resource(
    resource_id: int,
    body: UpdateBody,
    staff: Staff = Depends(WRITE),
    db: Session = Depends(get_db),
) -> dict:
    r = db.get(ReentryResource, resource_id)
    if not r:
        raise HTTPException(404, "not found")
    for field in ("title", "description", "phone", "address", "category", "enabled"):
        val = getattr(body, field)
        if val is not None:
            setattr(r, field, val)
    append_audit(
        db,
        Actor(staff.id, staff.role),
        "reentry_resource_updated",
        "reentry_resource",
        resource_id,
        payload={"title": r.title},
    )
    db.commit()
    return _row(r)


def _row(r: ReentryResource) -> dict:
    return {
        "id": r.id,
        "title": r.title,
        "description": r.description,
        "phone": r.phone,
        "address": r.address,
        "category": r.category,
        "enabled": r.enabled,
        "created_at": r.created_at.isoformat(),
    }
