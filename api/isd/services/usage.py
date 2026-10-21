"""How much of each allowance a resident has used in the current period. Read-only."""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from isd.engine.calls import effective_seconds
from isd.engine.periods import period_start
from isd.models import CallRecord, CommissaryOrder, Message


def call_seconds_today(session: Session, resident_id: int, at_time: datetime) -> int:
    """Seconds of non-privileged calls today. Attorney calls never count against the allowance."""
    rows = session.execute(
        select(CallRecord).where(
            CallRecord.resident_id == resident_id,
            CallRecord.privileged.is_(False),
            CallRecord.medium == "voice",
            CallRecord.started_at >= period_start(at_time, "day"),
            CallRecord.started_at <= at_time,
        )
    ).scalars()
    total = 0
    for r in rows:
        if r.duration_seconds is not None:
            total += r.duration_seconds
        else:  # still open: counts up to its cap
            total += effective_seconds(r.started_at, at_time, r.max_seconds)
    return total


def spent_cents_this_week(session: Session, resident_id: int, at_time: datetime) -> int:
    return (
        session.execute(
            select(func.coalesce(func.sum(CommissaryOrder.total_cents), 0)).where(
                CommissaryOrder.resident_id == resident_id,
                CommissaryOrder.created_at >= period_start(at_time, "week"),
                CommissaryOrder.created_at <= at_time,
            )
        ).scalar()
        or 0
    )


def video_seconds_this_week(session: Session, resident_id: int, at_time: datetime) -> int:
    rows = session.execute(
        select(CallRecord).where(
            CallRecord.resident_id == resident_id,
            CallRecord.medium == "video",
            CallRecord.started_at >= period_start(at_time, "week"),
            CallRecord.started_at <= at_time,
        )
    ).scalars()
    return sum(
        r.duration_seconds
        if r.duration_seconds is not None
        else effective_seconds(r.started_at, at_time, r.max_seconds)
        for r in rows
    )


def messages_sent_today(session: Session, resident_id: int, at_time: datetime) -> int:
    return (
        session.execute(
            select(func.count()).where(
                Message.resident_id == resident_id,
                Message.direction == "out",
                Message.created_at >= period_start(at_time, "day"),
                Message.created_at <= at_time,
            )
        ).scalar()
        or 0
    )
