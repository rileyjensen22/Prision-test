"""Education, calls and commissary endpoints for the resident kiosk (device-authenticated)."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from isd.auth import DeviceContext, current_device
from isd.db import get_db
from isd.engine.calls import CallDenied
from isd.engine.commissary import OrderError
from isd.engine.contacts import ContactInvalid
from isd.models import CallRecord, Contact
from isd.services import calls, commissary, contacts, education
from isd.services.education import EducationError

router = APIRouter(prefix="/device", tags=["device-features"])


def _conflict(e: Exception) -> HTTPException:
    status = 404 if getattr(e, "code", "") == "NOT_FOUND" else 409
    return HTTPException(status, {"code": getattr(e, "code", "ERROR"), "message": str(e)})


def _now() -> datetime:
    return datetime.now(UTC)


# ---------------- education ----------------
@router.get("/courses")
def list_courses(ctx: DeviceContext = Depends(current_device), db: Session = Depends(get_db)):
    return education.list_courses(db, ctx.resident_id, _now())


@router.get("/courses/{code}")
def get_course(
    code: str, ctx: DeviceContext = Depends(current_device), db: Session = Depends(get_db)
):
    try:
        return education.get_course(db, ctx.resident_id, code, _now())
    except EducationError as e:
        raise _conflict(e) from e


@router.post("/courses/{code}/lessons/{lesson_id}/complete")
def complete_lesson(
    code: str,
    lesson_id: str,
    ctx: DeviceContext = Depends(current_device),
    db: Session = Depends(get_db),
):
    try:
        return education.complete_lesson(db, ctx.resident_id, code, lesson_id, _now())
    except EducationError as e:
        raise _conflict(e) from e


class QuizIn(BaseModel):
    answers: list[int]


@router.post("/courses/{code}/quiz")
def submit_quiz(
    code: str,
    body: QuizIn,
    ctx: DeviceContext = Depends(current_device),
    db: Session = Depends(get_db),
):
    try:
        return education.submit_quiz(db, ctx.resident_id, code, body.answers, _now())
    except EducationError as e:
        raise _conflict(e) from e


# ---------------- calls ----------------
def _contact_out(c: Contact) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "type": c.type,
        "available": not c.blocked or c.type == "attorney",
    }


def _call_out(c: CallRecord) -> dict:
    return {
        "call_id": c.id,
        "privileged": c.privileged,
        "monitored": c.monitored,
        "max_seconds": c.max_seconds,
        "started_at": c.started_at.isoformat(),
        "status": c.status,
        "duration_seconds": c.duration_seconds,
    }


@router.get("/contacts")
def list_contacts(ctx: DeviceContext = Depends(current_device), db: Session = Depends(get_db)):
    return [_contact_out(c) for c in calls.list_contacts(db, ctx.resident_id)]


class ContactRequestIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=64)
    type: str = Field(max_length=16)
    phone: str = Field(min_length=1, max_length=20)


@router.get("/contacts/all")
def all_contacts(ctx: DeviceContext = Depends(current_device), db: Session = Depends(get_db)):
    """Every contact with its review status, for the contacts screen."""
    return [
        {
            "id": c.id,
            "name": c.name,
            "type": c.type,
            "status": c.status,
            "available": c.status == "approved" and (not c.blocked or c.type == "attorney"),
            "note": c.review_note if c.status == "rejected" else None,
        }
        for c in contacts.all_for_resident(db, ctx.resident_id)
    ]


@router.post("/contacts", status_code=201)
def request_contact(
    body: ContactRequestIn,
    ctx: DeviceContext = Depends(current_device),
    db: Session = Depends(get_db),
):
    try:
        c = contacts.request_contact(db, ctx.resident_id, body.name, body.type, body.phone, _now())
    except ContactInvalid as e:
        raise HTTPException(409, {"code": e.code, "message": str(e)}) from e
    return {"id": c.id, "status": c.status}


class CallIn(BaseModel):
    contact_id: int


@router.post("/calls", status_code=201)
def start_call(
    body: CallIn, ctx: DeviceContext = Depends(current_device), db: Session = Depends(get_db)
):
    try:
        return _call_out(calls.start_call(db, ctx.resident_id, body.contact_id, _now()))
    except CallDenied as e:
        raise _conflict(e) from e


@router.post("/calls/{call_id}/end")
def end_call(
    call_id: int, ctx: DeviceContext = Depends(current_device), db: Session = Depends(get_db)
):
    try:
        return _call_out(calls.end_call(db, ctx.resident_id, call_id, _now()))
    except CallDenied as e:
        raise _conflict(e) from e


# ---------------- commissary ----------------
@router.get("/commissary")
def commissary_view(ctx: DeviceContext = Depends(current_device), db: Session = Depends(get_db)):
    return commissary.catalog_view(db, ctx.resident_id, _now())


class OrderIn(BaseModel):
    client_id: str = Field(min_length=8, max_length=64)
    lines: dict[str, int]


@router.post("/commissary/orders", status_code=201)
def place_order(
    body: OrderIn, ctx: DeviceContext = Depends(current_device), db: Session = Depends(get_db)
):
    try:
        order = commissary.place_order(db, ctx.resident_id, body.lines, body.client_id, _now())
    except OrderError as e:
        raise _conflict(e) from e
    return {
        "order_id": order.id,
        "total_cents": order.total_cents,
        "balance_cents": commissary.balance_cents(db, ctx.resident_id),
    }
