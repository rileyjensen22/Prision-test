"""Device endpoints for grievances — baseline feature (invariant 1)."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from isd.auth import current_device
from isd.db import get_db
from isd.models import Grievance

router = APIRouter()

_VALID_CATEGORIES = {"conditions", "staff_conduct", "medical", "programs", "other"}


@router.post("/device/grievance")
def submit_grievance(
    body: dict,
    ctx=Depends(current_device),
    db: Session = Depends(get_db),
):
    category = body.get("category", "other")
    if category not in _VALID_CATEGORIES:
        category = "other"
    description = str(body.get("description", "")).strip()
    g = Grievance(
        resident_id=ctx.resident_id,
        category=category,
        description=description,
        status="open",
    )
    db.add(g)
    db.commit()
    db.refresh(g)
    return {"id": g.id, "status": g.status}


@router.get("/device/grievances")
def list_grievances(
    ctx=Depends(current_device),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(Grievance)
        .filter(Grievance.resident_id == ctx.resident_id)
        .order_by(Grievance.created_at.desc())
        .limit(20)
        .all()
    )
    return [
        {
            "id": r.id,
            "category": r.category,
            "status": r.status,
            "created_at": r.created_at.isoformat(),
            "response": r.response,
        }
        for r in rows
    ]
