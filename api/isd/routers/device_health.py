"""Device endpoints for health requests — baseline feature (invariant 1)."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from isd.auth import current_device
from isd.db import get_db
from isd.models import HealthRequest

router = APIRouter()


@router.post("/device/health-request")
def submit_health_request(
    body: dict,
    ctx=Depends(current_device),
    db: Session = Depends(get_db),
):
    kind = body.get("kind", "medical")
    if kind not in ("medical", "mental_health"):
        kind = "medical"
    description = str(body.get("description", "")).strip()
    hr = HealthRequest(
        resident_id=ctx.resident_id,
        kind=kind,
        description=description,
        status="open",
    )
    db.add(hr)
    db.commit()
    db.refresh(hr)
    return {"id": hr.id, "status": hr.status}


@router.get("/device/health-requests")
def list_health_requests(
    ctx=Depends(current_device),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(HealthRequest)
        .filter(HealthRequest.resident_id == ctx.resident_id)
        .order_by(HealthRequest.created_at.desc())
        .limit(20)
        .all()
    )
    return [
        {
            "id": r.id,
            "kind": r.kind,
            "status": r.status,
            "created_at": r.created_at.isoformat(),
            "staff_note": r.staff_note,
        }
        for r in rows
    ]
