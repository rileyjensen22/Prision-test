"""Simulated external events. In production these arrive from real providers, not staff clicks."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from isd.auth import require_roles
from isd.db import get_db
from isd.engine.commissary import OrderError
from isd.models import Staff
from isd.services import commissary
from isd.services.audit import Actor

router = APIRouter(prefix="/mock", tags=["mock"])


class DepositIn(BaseModel):
    resident_id: int
    amount_cents: int
    payer_ref: str = Field(min_length=1, max_length=64)
    idempotency_key: str = Field(min_length=8, max_length=64)


@router.post("/deposits", status_code=201)
def simulate_family_deposit(
    body: DepositIn,
    staff: Staff = Depends(require_roles("admin", "supervisor")),
    db: Session = Depends(get_db),
) -> dict:
    try:
        row = commissary.deposit(
            db,
            Actor(staff.id, staff.role),
            body.resident_id,
            body.amount_cents,
            body.payer_ref,
            body.idempotency_key,
            datetime.now(UTC),
        )
    except OrderError as e:
        raise HTTPException(422, {"code": e.code, "message": str(e)}) from e
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    return {"ref": row.ref, "balance_cents": row.balance_after_cents}
