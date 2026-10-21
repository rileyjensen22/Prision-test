"""Request-staff / medical / mental-health requests from the resident device (baseline features)."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from isd.models import StaffRequest


def create(
    session: Session, resident_id: int, kind: str, client_id: str, created_at: datetime
) -> tuple[StaffRequest, bool]:
    """Returns (request, duplicate). Replaying the same client_id is harmless (offline queue)."""
    existing = session.execute(
        select(StaffRequest).where(StaffRequest.client_id == client_id)
    ).scalar()
    if existing:
        return existing, True
    row = StaffRequest(
        resident_id=resident_id, kind=kind, client_id=client_id, created_at=created_at
    )
    session.add(row)
    session.flush()
    return row, False
