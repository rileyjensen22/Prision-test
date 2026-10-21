"""The daily job: clean-day points, tier checks (so delayed drops happen), and housekeeping.

Run it once a day shortly after midnight for the day that just ended (`make daily`). Every step
is safe to repeat: running it twice for the same day changes nothing the second time.
"""

from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from isd.models import DeviceAssignment, MirrorSession, PointEvent, Resident
from isd.services import calls, mirror
from isd.services.audit import SYSTEM
from isd.services.entitlement_service import load_engine_config
from isd.services.points import add_point_event, evaluate_tier

INFRACTION_KINDS = ("confirmed_minor_infraction", "confirmed_major_infraction")


def _day_bounds(day: date, tz) -> tuple[datetime, datetime]:
    start = datetime.combine(day, datetime.min.time(), tzinfo=tz)
    return start, start + timedelta(days=1)


def has_confirmed_infraction(session: Session, resident_id: int, day: date, tz) -> bool:
    start, end = _day_bounds(day, tz)
    return (
        session.execute(
            select(func.count()).where(
                PointEvent.resident_id == resident_id,
                PointEvent.kind.in_(INFRACTION_KINDS),
                PointEvent.created_at >= start,
                PointEvent.created_at < end,
            )
        ).scalar()
        > 0
    )


def clean_day_awarded(session: Session, resident_id: int, day: date) -> bool:
    return (
        session.execute(
            select(PointEvent.id).where(
                PointEvent.resident_id == resident_id,
                PointEvent.kind == "clean_day",
                PointEvent.reason == day.isoformat(),
            )
        ).first()
        is not None
    )


def run_daily(session: Session, now: datetime, for_day: date | None = None) -> dict:
    """`for_day` is the day that just ended (default: yesterday). `now` is when the job runs."""
    day = for_day or (now - timedelta(days=1)).date()
    cfg = load_engine_config(session)
    awarded = skipped_infraction = 0
    residents = session.execute(select(Resident.id).order_by(Resident.id)).scalars().all()
    for rid in residents:
        first = session.execute(
            select(func.min(DeviceAssignment.assigned_at)).where(
                DeviceAssignment.resident_id == rid
            )
        ).scalar()
        if first is None or first.date() > day:
            continue  # no device yet on that day
        if has_confirmed_infraction(session, rid, day, now.tzinfo):
            skipped_infraction += 1
        elif not clean_day_awarded(session, rid, day):
            add_point_event(session, SYSTEM, rid, "clean_day", now, reason=day.isoformat(), cfg=cfg)
            awarded += 1
        evaluate_tier(session, rid, now, cfg)  # applies promotions and the delayed weekly drop
        calls.settle_open_calls(session, rid, now)  # close calls the device never ended
    closed = 0
    for m in session.execute(
        select(MirrorSession).where(MirrorSession.ended_at.is_(None))
    ).scalars():
        try:
            mirror.frame(
                session, _as_actor(session, m), m.id, now
            )  # closes it if over time or idle
        except mirror.MirrorError:
            closed += 1
    return {
        "day": day.isoformat(),
        "clean_days_awarded": awarded,
        "skipped_for_infraction": skipped_infraction,
        "mirror_sessions_closed": closed,
    }


def _as_actor(session: Session, m: MirrorSession):
    from isd.models import Staff
    from isd.services.audit import Actor

    st = session.get(Staff, m.staff_id)
    return Actor(st.id, st.role)
