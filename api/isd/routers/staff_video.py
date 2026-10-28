"""Video call oversight. Supervisor + admin + auditor.
Attorney (privileged) video calls are excluded from this view per invariant 6."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from isd.auth import require_roles
from isd.db import get_db
from isd.models import CallRecord, Staff

router = APIRouter(prefix="/staff/video", tags=["staff-video"])
READ = require_roles("supervisor", "admin", "auditor")


@router.get("/sessions")
def list_sessions(
    resident_id: int | None = None,
    staff: Staff = Depends(READ),
    db: Session = Depends(get_db),
) -> list[dict]:
    """Video sessions only. Attorney calls (privileged=True) are excluded."""
    q = db.query(CallRecord).filter(
        CallRecord.medium == "video",
        CallRecord.privileged.is_(False),
    )
    if resident_id:
        q = q.filter(CallRecord.resident_id == resident_id)
    return [
        {
            "id": r.id,
            "resident_id": r.resident_id,
            "contact_id": r.contact_id,
            "duration_seconds": r.duration_seconds,
            "started_at": r.started_at.isoformat(),
            "ended_at": r.ended_at.isoformat() if r.ended_at else None,
            "status": r.status,
            "monitored": r.monitored,
        }
        for r in q.order_by(CallRecord.started_at.desc()).limit(200).all()
    ]
