"""Resident activity timeline for authorised staff: metadata only, and every look is audit-logged.

Never included: message text, call content, contact names or numbers. Attorney calls appear only
as "an attorney call happened, and for how long" (invariant 6).
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from isd.models import (
    CallRecord,
    ChessGame,
    CommissaryOrder,
    Contact,
    Message,
    OutOfCellLog,
    PointEvent,
    QuizAttempt,
    ReadingLog,
    Sanction,
    StaffRequest,
    TierHistory,
)
from isd.services.audit import Actor, append_audit

TIMELINE_ROLES = ("supervisor", "admin", "auditor")


class TimelineDenied(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def timeline(
    session: Session, actor: Actor, resident_id: int, reason: str, now: datetime, limit: int = 200
) -> list[dict]:
    if actor.role not in TIMELINE_ROLES:
        raise TimelineDenied("ROLE_NOT_PERMITTED", "this role cannot view activity")
    if len(reason.strip()) < 5:
        raise TimelineDenied("REASON_REQUIRED", "give a reason for viewing this activity")
    ev: list[dict] = []

    def add(at: datetime, kind: str, **detail):
        ev.append({"at": at, "kind": kind, "detail": detail})

    for c in session.execute(
        select(CallRecord).where(CallRecord.resident_id == resident_id)
    ).scalars():
        add(
            c.started_at,
            "video call" if c.medium == "video" else "call",
            contact_type=c.contact_type,
            privileged=c.privileged,
            monitored=c.monitored,
            seconds=c.duration_seconds,
        )
    for m, ctype in session.execute(
        select(Message, Contact.type)
        .join(Contact, Contact.id == Message.contact_id)
        .where(Message.resident_id == resident_id)
    ).all():
        add(
            m.created_at,
            "text message",
            direction=m.direction,
            contact_type=ctype,
            privileged=m.privileged,
            monitored=m.monitored,
        )  # no text, ever
    for o in session.execute(
        select(CommissaryOrder).where(CommissaryOrder.resident_id == resident_id)
    ).scalars():
        add(o.created_at, "commissary order", total_cents=o.total_cents)
    for q in session.execute(
        select(QuizAttempt).where(QuizAttempt.resident_id == resident_id)
    ).scalars():
        add(q.at, "quiz", course=q.course_code, passed=q.passed)
    for r in session.execute(
        select(StaffRequest).where(StaffRequest.resident_id == resident_id)
    ).scalars():
        add(r.created_at, "staff request", request=r.kind)
    for r in session.execute(
        select(ReadingLog).where(ReadingLog.resident_id == resident_id)
    ).scalars():
        add(r.at, "reading", item=r.item_id)
    for g in session.execute(
        select(ChessGame).where(ChessGame.resident_id == resident_id)
    ).scalars():
        add(g.created_at, "chess game", opponent=g.opponent_kind)
    for s in session.execute(select(Sanction).where(Sanction.resident_id == resident_id)).scalars():
        add(s.issued_at, "sanction", code=s.infraction_code, status=s.status)
    for t in session.execute(
        select(TierHistory).where(TierHistory.resident_id == resident_id)
    ).scalars():
        add(t.at, "tier change", frm=t.from_tier, to=t.to_tier)
    for p in session.execute(
        select(PointEvent).where(PointEvent.resident_id == resident_id)
    ).scalars():
        add(p.created_at, "points", event=p.kind, points=p.points)
    for d in session.execute(
        select(OutOfCellLog).where(OutOfCellLog.resident_id == resident_id)
    ).scalars():
        add(d.created_at, "out of cell", day=d.day.isoformat(), minutes=d.minutes)
    # Job participation is left out on purpose: it is voluntary and must not become a record.

    ev.sort(key=lambda e: e["at"], reverse=True)
    ev = ev[: min(limit, 500)]
    append_audit(
        session,
        actor,
        "monitoring_access",
        "resident",
        resident_id,
        "TIMELINE_VIEW",
        payload={"reason": reason.strip(), "entries": len(ev)},
    )
    return [{**e, "at": e["at"].isoformat()} for e in ev]
