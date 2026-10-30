"""Commissary order queue and deposit imports. commissary_clerk + supervisor + admin."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from isd.auth import require_roles
from isd.db import get_db
from isd.models import CommissaryOrder, DepositImport, Staff, TrustLedger
from isd.services.audit import Actor, append_audit

router = APIRouter(prefix="/staff/commissary", tags=["staff-commissary"])
READ = require_roles("commissary_clerk", "supervisor", "admin", "auditor")
WRITE = require_roles("commissary_clerk", "supervisor", "admin")

_MAX_DEPOSIT_CENTS = 50_000  # $500


class OrderUpdateBody(BaseModel):
    status: str | None = None
    refund_reason: str | None = None


class DepositRow(BaseModel):
    resident_id: int
    amount_cents: int


class DepositPreviewBody(BaseModel):
    rows: list[DepositRow]


class DepositApplyBody(BaseModel):
    filename: str = "import.csv"
    rows: list[DepositRow]


def _current_balance(db: Session, resident_id: int) -> int:
    row = db.execute(
        select(TrustLedger.balance_after_cents)
        .where(TrustLedger.resident_id == resident_id)
        .order_by(TrustLedger.id.desc())
        .limit(1)
    ).scalar()
    return row or 0


@router.get("/orders")
def list_orders(
    status: str | None = None,
    staff: Staff = Depends(READ),
    db: Session = Depends(get_db),
) -> list[dict]:
    q = db.query(CommissaryOrder)
    if status:
        q = q.filter(CommissaryOrder.status == status)
    return [_order_row(o) for o in q.order_by(CommissaryOrder.created_at.desc()).all()]


@router.patch("/orders/{order_id}")
def update_order(
    order_id: int,
    body: OrderUpdateBody,
    staff: Staff = Depends(WRITE),
    db: Session = Depends(get_db),
) -> dict:
    o = db.get(CommissaryOrder, order_id)
    if not o:
        raise HTTPException(404, "not found")
    if body.status is not None:
        o.status = body.status
        o.staff_id = staff.id
        o.updated_at = datetime.now(UTC)
        if body.status == "refunded":
            reason = body.refund_reason or ""
            o.refund_reason = reason
            # Post refund to append-only ledger
            bal = _current_balance(db, o.resident_id)
            entry = TrustLedger(
                resident_id=o.resident_id,
                entry_type="refund",
                amount_cents=o.total_cents,
                balance_after_cents=bal + o.total_cents,
                order_id=o.id,
                memo=f"Refund order #{o.id}: {reason}",
                created_by=staff.id,
                created_at=datetime.now(UTC),
            )
            db.add(entry)
            append_audit(
                db,
                Actor(staff.id, staff.role),
                "commissary_refund",
                "commissary_order",
                order_id,
                reason_code="REFUND",
                payload={"amount_cents": o.total_cents, "reason": reason},
            )
        else:
            append_audit(
                db,
                Actor(staff.id, staff.role),
                "commissary_order_update",
                "commissary_order",
                order_id,
                payload={"status": body.status},
            )
    db.commit()
    return _order_row(o)


@router.get("/deposits")
def list_deposits(
    staff: Staff = Depends(READ),
    db: Session = Depends(get_db),
) -> list[dict]:
    return [_deposit_row(d) for d in db.query(DepositImport).order_by(DepositImport.created_at.desc()).all()]


@router.post("/deposits/preview")
def preview_deposit(
    body: DepositPreviewBody,
    staff: Staff = Depends(WRITE),
    db: Session = Depends(get_db),
) -> dict:
    """Validate a deposit batch. Returns errors if any. Does NOT apply to ledger."""
    errors = []
    for i, row in enumerate(body.rows):
        if row.amount_cents <= 0 or row.amount_cents > _MAX_DEPOSIT_CENTS:
            errors.append({"row": i, "error": f"amount_cents {row.amount_cents} out of range (1–{_MAX_DEPOSIT_CENTS})"})
    total = sum(r.amount_cents for r in body.rows)
    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "row_count": len(body.rows),
        "total_cents": total,
    }


@router.post("/deposits/apply")
def apply_deposit(
    body: DepositApplyBody,
    staff: Staff = Depends(WRITE),
    db: Session = Depends(get_db),
) -> dict:
    """Apply a validated deposit batch. Validates again before writing."""
    for i, row in enumerate(body.rows):
        if row.amount_cents <= 0 or row.amount_cents > _MAX_DEPOSIT_CENTS:
            raise HTTPException(422, f"Row {i}: amount_cents {row.amount_cents} invalid")
    total = sum(r.amount_cents for r in body.rows)
    imp = DepositImport(
        filename=body.filename,
        imported_by=staff.id,
        row_count=len(body.rows),
        total_cents=total,
        status="applied",
        applied_at=datetime.now(UTC),
    )
    db.add(imp)
    db.flush()
    for row in body.rows:
        bal = _current_balance(db, row.resident_id)
        entry = TrustLedger(
            resident_id=row.resident_id,
            entry_type="deposit",
            amount_cents=row.amount_cents,
            balance_after_cents=bal + row.amount_cents,
            memo=f"Import {body.filename}",
            created_by=staff.id,
            created_at=datetime.now(UTC),
        )
        db.add(entry)
        db.flush()
    append_audit(
        db,
        Actor(staff.id, staff.role),
        "deposit_import_applied",
        "deposit_import",
        imp.id,
        payload={"filename": body.filename, "row_count": len(body.rows), "total_cents": total},
    )
    db.commit()
    return {"id": imp.id, "row_count": len(body.rows), "total_cents": total}


def _order_row(o: CommissaryOrder) -> dict:
    return {
        "id": o.id,
        "resident_id": o.resident_id,
        "total_cents": o.total_cents,
        "status": o.status,
        "staff_id": o.staff_id,
        "refund_reason": o.refund_reason,
        "created_at": o.created_at.isoformat(),
        "updated_at": o.updated_at.isoformat() if o.updated_at else None,
    }


def _deposit_row(d: DepositImport) -> dict:
    return {
        "id": d.id,
        "filename": d.filename,
        "imported_by": d.imported_by,
        "row_count": d.row_count,
        "total_cents": d.total_cents,
        "status": d.status,
        "created_at": d.created_at.isoformat(),
        "applied_at": d.applied_at.isoformat() if d.applied_at else None,
    }
