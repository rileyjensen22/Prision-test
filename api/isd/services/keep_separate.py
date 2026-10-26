"""Keep-separate entries: pairs of residents who must never be paired, scheduled or housed
together. Staff add and end them; every change is audited, nothing is deleted. The reason is
staff-only text and is never shown to a resident or put in the audit payload."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from isd.models import KeepSeparate, Resident
from isd.services.audit import Actor, append_audit
from isd.services.intake import IntakeError


class SeparateError(IntakeError):
    pass


def _by_code(session: Session, code: str) -> Resident:
    r = session.execute(select(Resident).where(Resident.code == code)).scalar()
    if r is None:
        raise SeparateError("NOT_FOUND", f"no resident with code {code}")
    return r


def list_open(session: Session, include_ended: bool = False) -> list[dict]:
    a, b = aliased(Resident), aliased(Resident)
    q = (
        select(KeepSeparate, a.code, b.code)
        .join(a, a.id == KeepSeparate.resident_a_id)
        .join(b, b.id == KeepSeparate.resident_b_id)
        .order_by(KeepSeparate.id)
    )
    if not include_ended:
        q = q.where(KeepSeparate.ended_at.is_(None))
    return [
        {
            "id": k.id,
            "a": ca,
            "b": cb,
            "reason": k.reason,
            "added_at": k.added_at.isoformat(),
            "ended_at": k.ended_at.isoformat() if k.ended_at else None,
        }
        for k, ca, cb in session.execute(q)
    ]


def add(
    session: Session, actor: Actor, code_a: str, code_b: str, reason: str, now: datetime
) -> KeepSeparate:
    if code_a == code_b:
        raise SeparateError("SAME_RESIDENT", "choose two different residents")
    if len(reason.strip()) < 3:
        raise SeparateError("REASON_REQUIRED", "give a reason (staff only)")
    ra, rb = _by_code(session, code_a), _by_code(session, code_b)
    lo, hi = sorted((ra.id, rb.id))
    exists = session.execute(
        select(KeepSeparate.id).where(
            KeepSeparate.resident_a_id == lo,
            KeepSeparate.resident_b_id == hi,
            KeepSeparate.ended_at.is_(None),
        )
    ).first()
    if exists:
        raise SeparateError("ALREADY_ENTERED", "these two residents are already kept apart")
    row = KeepSeparate(
        resident_a_id=lo,
        resident_b_id=hi,
        added_by=actor.id,
        added_at=now,
        reason=reason.strip()[:200],
    )
    session.add(row)
    session.flush()
    append_audit(
        session,
        actor,
        "keep_separate_added",
        "resident",
        ra.code,
        reason_code="KEEP_SEPARATE",
        payload={"with": rb.code, "entry_id": row.id},  # the reason text stays out of the log
    )
    return row


def end(session: Session, actor: Actor, entry_id: int, reason: str, now: datetime) -> KeepSeparate:
    if len(reason.strip()) < 3:
        raise SeparateError("REASON_REQUIRED", "say why this entry is ending")
    row = session.get(KeepSeparate, entry_id)
    if row is None:
        raise SeparateError("NOT_FOUND", "entry not found")
    if row.ended_at is not None:
        raise SeparateError("ALREADY_ENDED", "this entry has already ended")
    row.ended_at, row.ended_by = now, actor.id
    a, b = session.get(Resident, row.resident_a_id), session.get(Resident, row.resident_b_id)
    append_audit(
        session,
        actor,
        "keep_separate_ended",
        "resident",
        a.code,
        reason_code="KEEP_SEPARATE_ENDED",
        payload={"with": b.code, "entry_id": row.id, "reason": reason.strip()[:200]},
    )
    session.flush()
    return row
