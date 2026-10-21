"""Welfare flags: sharp drops in a resident's own device use or contact, long silence, short or
missing out-of-cell time. Computed on demand; acknowledgements are recorded and audited."""

from collections import Counter
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from isd.engine.welfare import WelfareRules, activity_flags, out_of_cell_flags
from isd.models import (
    CallRecord,
    ChessGame,
    ChessMove,
    CommissaryOrder,
    DeviceAssignment,
    Message,
    QuizAttempt,
    ReadingLog,
    Resident,
    StaffRequest,
    WelfareAck,
)
from isd.services.audit import Actor, append_audit
from isd.services.config_store import get_current
from isd.services.out_of_cell import window

FLAG_TEXT = {
    "no_contact": "No contact with anyone outside",
    "usage_drop": "Device use has dropped sharply compared with their usual",
    "contact_drop": "Contact with others has dropped sharply compared with their usual",
    "out_of_cell_below": "Out-of-cell time below the minimum",
    "out_of_cell_unrecorded": "Out-of-cell time has not been recorded",
}


def _config(session: Session) -> dict:
    return get_current(session, "welfare").payload


def _contact_times(session: Session, rid: int, since: datetime) -> list[datetime]:
    calls = session.execute(
        select(CallRecord.started_at).where(
            CallRecord.resident_id == rid, CallRecord.started_at >= since
        )
    ).scalars()
    texts = session.execute(
        select(Message.created_at).where(
            Message.resident_id == rid, Message.direction == "out", Message.created_at >= since
        )
    ).scalars()
    return [*calls, *texts]


def _usage_times(session: Session, rid: int, since: datetime) -> list[datetime]:
    more = [
        select(CommissaryOrder.created_at).where(
            CommissaryOrder.resident_id == rid, CommissaryOrder.created_at >= since
        ),
        select(QuizAttempt.at).where(QuizAttempt.resident_id == rid, QuizAttempt.at >= since),
        select(StaffRequest.created_at).where(
            StaffRequest.resident_id == rid, StaffRequest.created_at >= since
        ),
        select(ReadingLog.at).where(ReadingLog.resident_id == rid, ReadingLog.at >= since),
        select(ChessMove.at)
        .join(ChessGame, ChessGame.id == ChessMove.game_id)
        .where(ChessGame.resident_id == rid, ChessMove.by == "resident", ChessMove.at >= since),
    ]
    out = _contact_times(session, rid, since)
    for q in more:
        out.extend(session.execute(q).scalars())
    return out


def _series(times: list[datetime], today: date, length: int) -> list[int]:
    counts = Counter((today - t.date()).days for t in times)
    return [counts.get(length - 1 - i, 0) for i in range(length)]  # oldest first


def last_contact_day(session: Session, rid: int) -> date | None:
    a = session.execute(
        select(func.max(CallRecord.started_at)).where(CallRecord.resident_id == rid)
    ).scalar()
    b = session.execute(
        select(func.max(Message.created_at)).where(
            Message.resident_id == rid, Message.direction == "out"
        )
    ).scalar()
    latest = max((x for x in (a, b) if x), default=None)
    return latest.date() if latest else None


def resident_flags(session: Session, rid: int, tracked_days: int, now: datetime) -> list[dict]:
    cfg = _config(session)
    rules = WelfareRules.from_config(cfg)
    today = now.date()
    since = datetime.combine(
        today - timedelta(days=rules.history_needed - 1), datetime.min.time(), tzinfo=now.tzinfo
    )
    usage = _series(_usage_times(session, rid, since), today, rules.history_needed)
    contact = _series(_contact_times(session, rid, since), today, rules.history_needed)
    last = last_contact_day(session, rid)
    since_contact = None if last is None else (today - last).days
    flags = activity_flags(usage, contact, since_contact, tracked_days, rules)

    minimum = int(get_current(session, "compliance").payload["min_out_of_cell_minutes_per_day"])
    # Only count days the resident has actually been on the unit.
    days = window(session, rid, today, min(rules.recent_days, max(1, tracked_days + 1)))
    flags += out_of_cell_flags(days, minimum, rules.out_of_cell_unrecorded_days)
    acked = _recent_acks(session, rid, now, int(cfg["ack_suppress_days"]))
    return [
        {"type": f.type, "severity": f.severity, "message": FLAG_TEXT[f.type], "detail": f.detail}
        for f in flags
        if f.type not in acked
    ]


def _recent_acks(session: Session, rid: int, now: datetime, days: int) -> set[str]:
    return set(
        session.execute(
            select(WelfareAck.flag_type).where(
                WelfareAck.resident_id == rid, WelfareAck.at > now - timedelta(days=days)
            )
        ).scalars()
    )


def all_flags(session: Session, now: datetime) -> list[dict]:
    out = []
    residents = session.execute(select(Resident).order_by(Resident.code)).scalars().all()
    for r in residents:
        first = session.execute(
            select(func.min(DeviceAssignment.assigned_at)).where(
                DeviceAssignment.resident_id == r.id
            )
        ).scalar()
        if first is None:
            continue  # no device, nothing to watch
        flags = resident_flags(session, r.id, (now.date() - first.date()).days, now)
        if flags:
            out.append({"resident_id": r.id, "code": r.code, "flags": flags})
    return out


def acknowledge(
    session: Session, actor: Actor, resident_id: int, flag_type: str, note: str, now: datetime
) -> WelfareAck:
    if flag_type not in FLAG_TEXT:
        raise ValueError("unknown flag type")
    if len(note.strip()) < 3:
        raise ValueError("write what was done (at least a few words)")
    ack = WelfareAck(
        resident_id=resident_id, flag_type=flag_type, staff_id=actor.id, note=note.strip(), at=now
    )
    session.add(ack)
    session.flush()
    append_audit(
        session,
        actor,
        "welfare_ack",
        "resident",
        resident_id,
        "WELFARE_ACK",
        payload={"flag": flag_type, "note": note.strip()},
    )
    return ack
