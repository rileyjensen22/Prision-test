"""Intake, release date, reentry checklist and keep-separate (staff). RBAC on every route."""

from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from isd.auth import require_roles
from isd.db import get_db
from isd.models import Resident, Staff
from isd.services import intake as intake_service
from isd.services import reentry
from isd.services.audit import Actor
from isd.services.intake import IntakeContact, IntakeError, IntakeRequest

router = APIRouter(prefix="/staff", tags=["intake"])


def _now() -> datetime:
    return datetime.now(UTC)


def _fail(e: Exception) -> HTTPException:
    code = getattr(e, "code", "ERROR")
    status = 404 if code == "NOT_FOUND" else 409 if code in {"OCCUPIED", "CODE_TAKEN"} else 422
    return HTTPException(status, {"code": code, "message": str(e)})


class ContactIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(max_length=64)
    type: str
    phone: str = Field(max_length=32)


class SeparateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resident_code: str
    reason: str = Field(max_length=200)


class IntakeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str = Field(max_length=128)
    cell_code: str
    device_code: str
    reason: str = Field(max_length=300)
    code: str | None = None
    language: str = Field(default="en", pattern="^(en|es)$")
    text_size: str = Field(default="normal", pattern="^(normal|large|xlarge)$")
    reading_level: str = Field(default="standard", pattern="^(simple|standard)$")
    captions: bool = False
    prior_returns: int = 0
    prior_returns_source: str | None = Field(default=None, max_length=128)
    release_date: date | None = None
    offense_categories: list[str] = Field(default_factory=list, max_length=10)
    contacts: list[ContactIn] = Field(default_factory=list, max_length=30)
    keep_separate: list[SeparateIn] = Field(default_factory=list, max_length=20)


@router.get("/intake/options")
def intake_options(
    staff: Staff = Depends(require_roles("supervisor", "admin")), db: Session = Depends(get_db)
):
    return intake_service.options(db)


@router.post("/intake", status_code=201)
def intake(
    body: IntakeIn,
    staff: Staff = Depends(require_roles("supervisor", "admin")),
    db: Session = Depends(get_db),
):
    req = IntakeRequest(
        display_name=body.display_name,
        cell_code=body.cell_code,
        device_code=body.device_code,
        reason=body.reason,
        code=body.code,
        language=body.language,
        text_size=body.text_size,
        reading_level=body.reading_level,
        captions=body.captions,
        prior_returns=body.prior_returns,
        prior_returns_source=body.prior_returns_source,
        release_date=body.release_date,
        offense_categories=body.offense_categories,
        contacts=[IntakeContact(c.name, c.type, c.phone) for c in body.contacts],
        keep_separate=[(k.resident_code, k.reason) for k in body.keep_separate],
    )
    try:
        resident = intake_service.intake(db, Actor(staff.id, staff.role), req, _now())
    except IntakeError as e:
        raise _fail(e) from e
    return {"resident_id": resident.id, "code": resident.code}


@router.get("/residents/{resident_id}/reentry")
def staff_reentry(
    resident_id: int,
    staff: Staff = Depends(require_roles("officer", "supervisor", "admin", "auditor")),
    db: Session = Depends(get_db),
):
    try:
        return reentry.staff_view(db, resident_id)
    except reentry.ReentryError as e:
        raise _fail(e) from e


class ReleaseDateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    release_date: date | None
    reason: str = Field(max_length=300)


@router.put("/residents/{resident_id}/release-date")
def set_release_date(
    resident_id: int,
    body: ReleaseDateIn,
    staff: Staff = Depends(require_roles("supervisor", "admin")),
    db: Session = Depends(get_db),
):
    try:
        reentry.set_release_date(
            db, Actor(staff.id, staff.role), resident_id, body.release_date, body.reason, _now()
        )
    except reentry.ReentryError as e:
        raise _fail(e) from e
    return {"release_date": body.release_date.isoformat() if body.release_date else None}


class ItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item_code: str
    status: str
    note: str | None = Field(default=None, max_length=500)


@router.post("/residents/{resident_id}/reentry-items", status_code=201)
def record_item(
    resident_id: int,
    body: ItemIn,
    staff: Staff = Depends(require_roles("officer", "supervisor", "admin")),
    db: Session = Depends(get_db),
):
    try:
        reentry.record_item(
            db,
            Actor(staff.id, staff.role),
            resident_id,
            body.item_code,
            body.status,
            body.note,
            _now(),
        )
    except reentry.ReentryError as e:
        raise _fail(e) from e
    return reentry.staff_view(db, resident_id)


@router.get("/residents/{resident_id}/keep-separate")
def keep_separate(
    resident_id: int,
    staff: Staff = Depends(require_roles("supervisor", "admin", "auditor")),
    db: Session = Depends(get_db),
):
    if db.get(Resident, resident_id) is None:
        raise HTTPException(404, {"code": "NOT_FOUND", "message": "resident not found"})
    return {"codes": intake_service.keep_separate_codes(db, resident_id)}
