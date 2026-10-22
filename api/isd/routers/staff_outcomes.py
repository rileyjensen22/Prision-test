"""Outcomes dashboard, outcome entry and the researcher export (evaluation only)."""

import csv
import io
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from isd import settings
from isd.analytics import service
from isd.auth import require_roles
from isd.db import get_db
from isd.models import Staff
from isd.services.audit import Actor

router = APIRouter(prefix="/staff/outcomes", tags=["outcomes"])


def _now() -> datetime:
    return datetime.now(UTC)


def _fail(e: service.OutcomeError) -> HTTPException:
    status = {"NOT_FOUND": 404, "EXPORT_DISABLED": 403}.get(e.code, 422)
    return HTTPException(status, {"code": e.code, "message": str(e)})


@router.get("")
def dashboard(
    staff: Staff = Depends(require_roles("supervisor", "admin", "auditor")),
    db: Session = Depends(get_db),
):
    return service.dashboard(db, _now())


class OutcomeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resident_code: str
    window_months: int
    outcome: str
    source: str = Field(max_length=80)


@router.post("", status_code=201)
def enter(
    body: OutcomeIn,
    staff: Staff = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    try:
        row = service.record_outcome(
            db,
            Actor(staff.id, staff.role),
            body.resident_code,
            body.window_months,
            body.outcome,
            body.source,
            _now(),
        )
    except service.OutcomeError as e:
        raise _fail(e) from e
    return {"id": row.id, "corrects": row.corrects_id}


@router.get("/export")
def export(
    reason: str,
    format: str = "json",
    staff: Staff = Depends(require_roles("admin", "auditor")),
    db: Session = Depends(get_db),
):
    try:
        data = service.export(
            db, Actor(staff.id, staff.role), reason, settings.RESEARCH_SALT, _now()
        )
    except service.OutcomeError as e:
        raise _fail(e) from e
    if format != "csv":
        return data
    rows = data["rows"]
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=list(rows[0]) if rows else ["pseudonym"])
    writer.writeheader()
    writer.writerows(rows)
    return Response(out.getvalue(), media_type="text/csv")
