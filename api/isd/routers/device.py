"""Endpoints called by the resident kiosk. Authenticated by device token, not by staff login."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from isd.auth import DeviceContext, current_device
from isd.db import get_db
from isd.engine.authority import AuthorityError
from isd.models import Sanction
from isd.schemas import ResidentView
from isd.services import sanctions, staff_requests
from isd.services.resident_view import build_resident_view

router = APIRouter(prefix="/device", tags=["device"])


@router.get("/view", response_model=ResidentView)
def view(ctx: DeviceContext = Depends(current_device), db: Session = Depends(get_db)):
    now = datetime.now(UTC)
    ctx.device.last_sync_at = now
    return build_resident_view(db, ctx.resident_id, now)


class AppealIn(BaseModel):
    sanction_id: int


@router.post("/appeals", status_code=201)
def appeal(
    body: AppealIn, ctx: DeviceContext = Depends(current_device), db: Session = Depends(get_db)
) -> dict:
    s = db.get(Sanction, body.sanction_id)
    if s is None or s.resident_id != ctx.resident_id:
        raise HTTPException(404, "sanction not found")
    try:
        a = sanctions.file_appeal(db, s.id, datetime.now(UTC))
    except AuthorityError as e:
        raise HTTPException(409, {"code": e.code, "message": str(e)}) from e
    return {"appeal_id": a.id, "due_at": a.due_at.isoformat()}


class RequestIn(BaseModel):
    kind: str = Field(pattern="^(staff|medical|mental_health)$")
    client_id: str = Field(min_length=8, max_length=64)  # lets the offline queue replay safely
    created_at: datetime | None = None


@router.post("/requests", status_code=201)
def request_staff(
    body: RequestIn, ctx: DeviceContext = Depends(current_device), db: Session = Depends(get_db)
) -> dict:
    try:
        row, duplicate = staff_requests.create(
            db, ctx.resident_id, body.kind, body.client_id, body.created_at or datetime.now(UTC)
        )
    except IntegrityError as e:  # concurrent replay of the same client_id
        raise HTTPException(409, "duplicate request") from e
    return {"request_id": row.id, "duplicate": duplicate}


class ScreenIn(BaseModel):
    path: str


@router.post("/screen", status_code=204)
def report_screen(
    body: ScreenIn, ctx: DeviceContext = Depends(current_device), db: Session = Depends(get_db)
) -> None:
    """The kiosk tells us which screen it is on, so a logged live mirror can follow along."""
    from isd.engine.mirror import is_valid_screen_path
    from isd.services.mirror import record_screen

    if not is_valid_screen_path(body.path):
        raise HTTPException(422, "invalid screen path")
    record_screen(db, ctx.device, body.path, datetime.now(UTC))
