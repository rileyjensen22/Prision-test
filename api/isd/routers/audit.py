from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from isd.auth import require_roles
from isd.db import get_db
from isd.models import AuditLog, Staff
from isd.services.audit import Actor, append_audit, verify_chain

router = APIRouter(prefix="/audit", tags=["audit"])
READERS = ("admin", "auditor")


def _out(r: AuditLog) -> dict:
    return {
        "seq": r.seq,
        "ts": r.ts.isoformat(),
        "actor_id": r.actor_id,
        "actor_role": r.actor_role,
        "action": r.action,
        "target_type": r.target_type,
        "target_id": r.target_id,
        "reason_code": r.reason_code,
        "ref_seq": r.ref_seq,
        "payload": r.payload,
        "hash": r.hash,
    }


@router.get("")
def list_entries(
    after_seq: int = 0,
    limit: int = 100,
    _: Staff = Depends(require_roles(*READERS)),
    db: Session = Depends(get_db),
) -> list[dict]:
    q = (
        select(AuditLog)
        .where(AuditLog.seq > after_seq)
        .order_by(AuditLog.seq)
        .limit(min(limit, 500))
    )
    return [_out(r) for r in db.execute(q).scalars()]


@router.get("/verify")
def verify(_: Staff = Depends(require_roles(*READERS)), db: Session = Depends(get_db)) -> dict:
    r = verify_chain(db)
    return {
        "ok": r.ok,
        "entries": r.entries,
        "first_bad_seq": r.first_bad_seq,
        "problem": r.problem,
    }


class CorrectionIn(BaseModel):
    ref_seq: int
    reason_code: str
    note: str


@router.post("/corrections", status_code=201)
def add_correction(
    body: CorrectionIn,
    staff: Staff = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
) -> dict:
    """The only way to 'fix' the log: a new entry referencing the original."""
    if db.get(AuditLog, body.ref_seq) is None:
        raise HTTPException(404, "referenced entry not found")
    row = append_audit(
        db,
        Actor(staff.id, staff.role),
        "correction",
        "audit_log",
        body.ref_seq,
        reason_code=body.reason_code,
        ref_seq=body.ref_seq,
        payload={"note": body.note},
    )
    return _out(row)
