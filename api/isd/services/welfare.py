"""Welfare flags: sharp drops in a resident's own device use or contact, long silence, short or
missing out-of-cell time. Computed on demand; acknowledgements are recorded and audited."""

from collections import Counter
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from isd.engine.welfare import (
    FlagRow,
    WelfareRules,
    activity_flags,
    out_of_cell_flags,
    plan_flag_sync,
)
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
    WelfareFlag,
)
from isd.services.audit import SYSTEM, Actor, append_audit
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


def detect(session: Session, rid: int, tracked_days: int, now: datetime) -> list[dict]:
    """What is true about this resident right now, compared with their own history. The usual
    levels (their baseline) are part of each flag's detail."""
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
    return [
        {"type": f.type, "severity": f.severity, "message": FLAG_TEXT[f.type], "detail": f.detail}
        for f in flags
    ]


def resident_flags(session: Session, rid: int, tracked_days: int, now: datetime) -> list[dict]:
    """What is true now, minus flags a person acknowledged recently (they stay quiet for
    `ack_suppress_days`)."""
    days = int(_config(session)["ack_suppress_days"])
    quiet = set(
        session.execute(
            select(WelfareFlag.flag_type).where(
                WelfareFlag.resident_id == rid,
                WelfareFlag.status == "acknowledged",
                WelfareFlag.acknowledged_at > now - timedelta(days=days),
            )
        ).scalars()
    )
    return [f for f in detect(session, rid, tracked_days, now) if f["type"] not in quiet]


def _tracked(session: Session, rid: int, now: datetime) -> int | None:
    first = session.execute(
        select(func.min(DeviceAssignment.assigned_at)).where(DeviceAssignment.resident_id == rid)
    ).scalar()
    return None if first is None else (now.date() - first.date()).days


def sync_flags(session: Session, now: datetime) -> dict:
    """Makes the stored flags match what is true now: raises new ones, escalates the ones nobody
    has acknowledged in time, and clears the ones that no longer apply. Safe to repeat."""
    cfg = _config(session)
    raised = escalated = cleared = 0
    for r in session.execute(select(Resident).order_by(Resident.id)).scalars().all():
        tracked = _tracked(session, r.id, now)
        if tracked is None:
            continue  # no device, nothing to watch
        found = {f["type"]: f for f in detect(session, r.id, tracked, now)}
        rows = (
            session.execute(select(WelfareFlag).where(WelfareFlag.resident_id == r.id))
            .scalars()
            .all()
        )
        by_id = {x.id: x for x in rows}
        rules = [
            FlagRow(x.id, x.flag_type, x.status, x.raised_at, x.acknowledged_at, x.escalated_at)
            for x in rows
        ]
        for action, kind, row_id in plan_flag_sync(
            set(found),
            rules,
            now,
            int(cfg["ack_suppress_days"]),
            int(cfg["escalate_after_minutes"]),
        ):
            if action == "raise":
                row = WelfareFlag(
                    resident_id=r.id,
                    flag_type=kind,
                    severity=found[kind]["severity"],
                    detail=found[kind]["detail"],
                    raised_at=now,
                )
                session.add(row)
                session.flush()
                append_audit(
                    session,
                    SYSTEM,
                    "welfare_flag_raised",
                    "resident",
                    r.id,
                    "WELFARE_FLAG",
                    payload={"flag_id": row.id, "type": kind},
                )
                raised += 1
            elif action == "escalate":
                by_id[row_id].escalated_at = now
                append_audit(
                    session,
                    SYSTEM,
                    "welfare_escalated",
                    "resident",
                    r.id,
                    "WELFARE_ESCALATED",
                    payload={
                        "flag_id": row_id,
                        "type": kind,
                        "minutes": int(cfg["escalate_after_minutes"]),
                    },
                )
                escalated += 1
            else:
                by_id[row_id].status, by_id[row_id].cleared_at = "cleared", now
                cleared += 1
    session.flush()
    return {"raised": raised, "escalated": escalated, "cleared": cleared}


def all_flags(session: Session, now: datetime) -> list[dict]:
    """Open flags (not yet acknowledged), grouped by resident. Escalated ones say so."""
    sync_flags(session, now)
    rows = session.execute(
        select(WelfareFlag, Resident.code)
        .join(Resident, Resident.id == WelfareFlag.resident_id)
        .where(WelfareFlag.status == "open")
        .order_by(Resident.code, WelfareFlag.id)
    ).all()
    out: dict[int, dict] = {}
    for f, code in rows:
        entry = out.setdefault(
            f.resident_id, {"resident_id": f.resident_id, "code": code, "flags": []}
        )
        entry["flags"].append(
            {
                "id": f.id,
                "type": f.flag_type,
                "severity": f.severity,
                "message": FLAG_TEXT[f.flag_type],
                "detail": f.detail,
                "raised_at": f.raised_at.isoformat(),
                "escalated": f.escalated_at is not None,
                "escalated_at": f.escalated_at.isoformat() if f.escalated_at else None,
            }
        )
    return list(out.values())


ACTIONS = (
    "checked_in",  # spoke with the resident
    "referred_medical",
    "referred_mental_health",
    "adjusted_schedule",
    "no_concern",
)


class WelfareError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def acknowledge(
    session: Session,
    actor: Actor,
    resident_id: int,
    flag_type: str,
    note: str,
    now: datetime,
    action: str = "checked_in",
) -> WelfareAck:
    """Staff must say what they did. An escalated flag can only be acknowledged by a supervisor
    or admin, since it went to them."""
    if flag_type not in FLAG_TEXT:
        raise WelfareError("BAD_FLAG", "unknown flag type")
    if action not in ACTIONS:
        raise WelfareError("BAD_ACTION", "choose what was done")
    if len(note.strip()) < 3:
        raise WelfareError("NOTE_REQUIRED", "write what was done (at least a few words)")
    sync_flags(session, now)
    flag = session.execute(
        select(WelfareFlag)
        .where(
            WelfareFlag.resident_id == resident_id,
            WelfareFlag.flag_type == flag_type,
            WelfareFlag.status == "open",
        )
        .order_by(WelfareFlag.id.desc())
        .limit(1)
        .with_for_update()
    ).scalar()
    if flag is None:
        raise WelfareError("NO_OPEN_FLAG", "there is no open flag of that kind")
    if flag.escalated_at is not None and actor.role not in ("supervisor", "admin"):
        raise WelfareError(
            "NEEDS_SUPERVISOR", "this flag was escalated; a supervisor must handle it"
        )
    flag.status, flag.acknowledged_at, flag.acknowledged_by = "acknowledged", now, actor.id
    flag.action, flag.note = action, note.strip()
    ack = WelfareAck(
        resident_id=resident_id,
        flag_type=flag_type,
        staff_id=actor.id,
        note=note.strip(),
        at=now,
        action=action,
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
        payload={"flag": flag_type, "flag_id": flag.id, "action": action, "note": note.strip()},
    )
    return ack
