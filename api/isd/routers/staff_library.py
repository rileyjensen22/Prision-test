"""Library management. legal_liaison uploads; a DIFFERENT staff member approves (two-person rule)."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from isd.auth import require_roles
from isd.db import get_db
from isd.models import LibraryItem, Staff
from isd.services.audit import Actor, append_audit

router = APIRouter(prefix="/staff/library", tags=["staff-library"])
READ = require_roles("legal_liaison", "supervisor", "admin", "auditor")
WRITE = require_roles("legal_liaison", "supervisor", "admin")


class CreateBody(BaseModel):
    title: str
    author: str = ""
    category: str = "general"
    language: str = "en"
    reading_level: str = "standard"
    content_text: str = ""


class UpdateBody(BaseModel):
    title: str | None = None
    author: str | None = None
    enabled: bool | None = None


@router.get("")
def list_items(
    approved: bool | None = None,
    staff: Staff = Depends(READ),
    db: Session = Depends(get_db),
) -> list[dict]:
    q = db.query(LibraryItem)
    if approved is not None:
        q = q.filter(LibraryItem.approved == approved)
    return [_row(i) for i in q.order_by(LibraryItem.created_at.desc()).all()]


@router.post("")
def create_item(
    body: CreateBody,
    staff: Staff = Depends(WRITE),
    db: Session = Depends(get_db),
) -> dict:
    item = LibraryItem(
        title=body.title,
        author=body.author,
        category=body.category,
        language=body.language,
        reading_level=body.reading_level,
        content_text=body.content_text,
        uploaded_by=staff.id,
        approved=False,
    )
    db.add(item)
    db.flush()
    append_audit(
        db,
        Actor(staff.id, staff.role),
        "library_item_created",
        "library_item",
        item.id,
        payload={"title": item.title},
    )
    db.commit()
    return _row(item)


@router.post("/{item_id}/approve")
def approve_item(
    item_id: int,
    staff: Staff = Depends(WRITE),
    db: Session = Depends(get_db),
) -> dict:
    item = db.get(LibraryItem, item_id)
    if not item:
        raise HTTPException(404, "not found")
    if item.uploaded_by == staff.id:
        raise HTTPException(403, "Approver must be different from uploader (two-person rule)")
    item.approved = True
    item.approved_by = staff.id
    item.updated_at = datetime.now(UTC)
    append_audit(
        db,
        Actor(staff.id, staff.role),
        "library_item_approved",
        "library_item",
        item_id,
        payload={"title": item.title},
    )
    db.commit()
    return _row(item)


@router.patch("/{item_id}")
def update_item(
    item_id: int,
    body: UpdateBody,
    staff: Staff = Depends(WRITE),
    db: Session = Depends(get_db),
) -> dict:
    item = db.get(LibraryItem, item_id)
    if not item:
        raise HTTPException(404, "not found")
    if body.title is not None:
        item.title = body.title
    if body.author is not None:
        item.author = body.author
    if body.enabled is not None:
        item.enabled = body.enabled
    item.updated_at = datetime.now(UTC)
    append_audit(
        db,
        Actor(staff.id, staff.role),
        "library_item_updated",
        "library_item",
        item_id,
        payload={"enabled": item.enabled},
    )
    db.commit()
    return _row(item)


def _row(i: LibraryItem) -> dict:
    return {
        "id": i.id,
        "title": i.title,
        "author": i.author,
        "category": i.category,
        "language": i.language,
        "reading_level": i.reading_level,
        "approved": i.approved,
        "approved_by": i.approved_by,
        "uploaded_by": i.uploaded_by,
        "enabled": i.enabled,
        "created_at": i.created_at.isoformat(),
    }
