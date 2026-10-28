"""Staff account administration (admins only)."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from isd.auth import require_roles
from isd.db import get_db
from isd.models import Staff
from isd.services import staff_accounts
from isd.services.audit import Actor

router = APIRouter(prefix="/staff/accounts", tags=["accounts"])
ADMIN = require_roles("admin")


def _now() -> datetime:
    return datetime.now(UTC)


def _fail(e: staff_accounts.AccountError) -> HTTPException:
    status = (
        404 if e.code == "NOT_FOUND" else 409 if e.code in {"USERNAME_TAKEN", "LAST_ADMIN"} else 422
    )
    return HTTPException(status, {"code": e.code, "message": str(e)})


class ReasonIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(max_length=300)


class CreateIn(ReasonIn):
    username: str = Field(max_length=64)
    role: str = Field(max_length=16)


class ActiveIn(ReasonIn):
    active: bool


@router.get("")
def list_accounts(staff: Staff = Depends(ADMIN), db: Session = Depends(get_db)) -> list[dict]:
    return staff_accounts.list_accounts(db)


@router.post("", status_code=201)
def create(body: CreateIn, staff: Staff = Depends(ADMIN), db: Session = Depends(get_db)) -> dict:
    try:
        row, temp = staff_accounts.create_account(
            db, Actor(staff.id, staff.role), body.username, body.role, body.reason, _now()
        )
    except staff_accounts.AccountError as e:
        raise _fail(e) from e
    return {"id": row.id, "username": row.username, "temporary_password": temp}


@router.post("/{staff_id}/active")
def active(
    staff_id: int, body: ActiveIn, staff: Staff = Depends(ADMIN), db: Session = Depends(get_db)
) -> dict:
    try:
        row = staff_accounts.set_active(
            db, Actor(staff.id, staff.role), staff_id, body.active, body.reason, _now()
        )
    except staff_accounts.AccountError as e:
        raise _fail(e) from e
    return {"id": row.id, "active": row.active}


@router.post("/{staff_id}/reset-password")
def reset_password(
    staff_id: int, body: ReasonIn, staff: Staff = Depends(ADMIN), db: Session = Depends(get_db)
) -> dict:
    try:
        temp = staff_accounts.reset_password(
            db, Actor(staff.id, staff.role), staff_id, body.reason, _now()
        )
    except staff_accounts.AccountError as e:
        raise _fail(e) from e
    return {"temporary_password": temp}


@router.post("/{staff_id}/reset-mfa")
def reset_mfa(
    staff_id: int, body: ReasonIn, staff: Staff = Depends(ADMIN), db: Session = Depends(get_db)
) -> dict:
    try:
        staff_accounts.reset_mfa(db, Actor(staff.id, staff.role), staff_id, body.reason, _now())
    except staff_accounts.AccountError as e:
        raise _fail(e) from e
    return {"reset": staff_id}
