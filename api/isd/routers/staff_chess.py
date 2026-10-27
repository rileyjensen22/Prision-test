"""Staff side of chess: the match log, the per-resident switch for human play, and cell lines."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from isd.auth import require_roles
from isd.db import get_db
from isd.models import Cell, Resident, Staff
from isd.services import chess
from isd.services.audit import Actor, append_audit

router = APIRouter(prefix="/staff", tags=["chess"])


def _now() -> datetime:
    return datetime.now(UTC)


@router.get("/chess/matches")
def match_log(
    limit: int = 100,
    offset: int = 0,
    staff: Staff = Depends(require_roles("supervisor", "admin", "auditor")),
    db: Session = Depends(get_db),
):
    return chess.match_log(db, min(max(limit, 1), 500), max(offset, 0))


class SwitchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    human: bool | None  # true = on, false = off, null = follow the unit and facility setting
    reason: str = Field(min_length=3, max_length=300)


@router.put("/residents/{resident_id}/chess")
def set_switch(
    resident_id: int,
    body: SwitchIn,
    staff: Staff = Depends(require_roles("supervisor", "admin")),
    db: Session = Depends(get_db),
):
    resident = db.get(Resident, resident_id)
    if resident is None:
        raise HTTPException(404, {"code": "NOT_FOUND", "message": "resident not found"})
    before = resident.chess_human
    resident.chess_human = body.human
    db.flush()
    append_audit(
        db,
        Actor(staff.id, staff.role),
        "chess_setting_changed",
        "resident",
        resident.code,
        reason_code="CHESS_SETTING",
        payload={"from": before, "to": body.human, "reason": body.reason},
    )
    return {"resident_id": resident.id, "chess_human": resident.chess_human}


class LineIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    line_code: str | None = Field(default=None, max_length=16, pattern=r"^[A-Za-z0-9_-]+$")
    reason: str = Field(min_length=3, max_length=300)


@router.get("/cells")
def cells(
    staff: Staff = Depends(require_roles("supervisor", "admin", "auditor")),
    db: Session = Depends(get_db),
):
    return [
        {"code": c.code, "unit": c.unit, "line_code": c.line_code}
        for c in db.execute(select(Cell).order_by(Cell.code)).scalars()
    ]


@router.put("/cells/{cell_code}/line")
def set_line(
    cell_code: str,
    body: LineIn,
    staff: Staff = Depends(require_roles("supervisor", "admin")),
    db: Session = Depends(get_db),
):
    cell = db.execute(select(Cell).where(Cell.code == cell_code)).scalar()
    if cell is None:
        raise HTTPException(404, {"code": "NOT_FOUND", "message": "cell not found"})
    before = cell.line_code
    cell.line_code = body.line_code
    db.flush()
    append_audit(
        db,
        Actor(staff.id, staff.role),
        "cell_line_changed",
        "cell",
        cell.code,
        reason_code="CELL_LINE",
        payload={"from": before, "to": body.line_code, "reason": body.reason},
    )
    return {"code": cell.code, "line_code": cell.line_code}
