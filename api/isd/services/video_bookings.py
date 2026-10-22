"""Scheduled video calls. Booked minutes are reserved against the weekly video allowance."""

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from isd.engine.calls import CallDenied
from isd.engine.periods import period_start
from isd.models import CallRecord, Contact, VideoBooking
from isd.services.calls import privileged_types, start_call
from isd.services.config_store import get_current
from isd.services.entitlement_service import get_entitlements


def _cfg(session: Session) -> dict:
    return get_current(session, "compliance").payload


def expire(session: Session, resident_id: int, now: datetime) -> None:
    """A booking whose slot has passed unused is missed; it stops holding minutes."""
    for b in session.execute(
        select(VideoBooking).where(
            VideoBooking.resident_id == resident_id, VideoBooking.status == "scheduled"
        )
    ).scalars():
        if b.starts_at + timedelta(minutes=b.minutes) < now:
            b.status = "missed"


def reserved_seconds(session: Session, resident_id: int, now: datetime, except_booking=None) -> int:
    """Minutes held by upcoming bookings in the current week (not the one being started)."""
    week = period_start(now, "week")
    q = select(func.coalesce(func.sum(VideoBooking.minutes), 0)).where(
        VideoBooking.resident_id == resident_id,
        VideoBooking.status == "scheduled",
        VideoBooking.starts_at >= week,
        VideoBooking.starts_at < week + timedelta(days=7),
        VideoBooking.starts_at + func.make_interval(0, 0, 0, 0, 0, VideoBooking.minutes) >= now,
    )
    if except_booking is not None:
        q = q.where(VideoBooking.id != except_booking.id)
    return int(session.execute(q).scalar() or 0) * 60


def _week_seconds(session: Session, resident_id: int, when: datetime) -> tuple[int, int]:
    """(seconds used, minutes already booked) in the week containing `when`."""
    week = period_start(when, "week")
    used = session.execute(
        select(func.coalesce(func.sum(CallRecord.duration_seconds), 0)).where(
            CallRecord.resident_id == resident_id,
            CallRecord.medium == "video",
            CallRecord.privileged.is_(False),
            CallRecord.started_at >= week,
            CallRecord.started_at < week + timedelta(days=7),
        )
    ).scalar()
    booked = session.execute(
        select(func.coalesce(func.sum(VideoBooking.minutes), 0)).where(
            VideoBooking.resident_id == resident_id,
            VideoBooking.status == "scheduled",
            VideoBooking.starts_at >= week,
            VideoBooking.starts_at < week + timedelta(days=7),
        )
    ).scalar()
    return int(used or 0), int(booked or 0)


def book(
    session: Session,
    resident_id: int,
    contact_id: int,
    starts_at: datetime,
    minutes: int,
    now: datetime,
) -> VideoBooking:
    cfg = _cfg(session)
    slot, longest = cfg["video_booking_slot_minutes"], cfg["video_booking_max_minutes"]
    expire(session, resident_id, now)
    contact = session.get(Contact, contact_id)
    if contact is None or contact.resident_id != resident_id or not contact.approved:
        raise CallDenied("CONTACT_UNAVAILABLE", "contact not available")
    privileged = contact.type in privileged_types(session)
    if contact.blocked and not privileged:
        raise CallDenied("CONTACT_UNAVAILABLE", "contact not available")
    feature = get_entitlements(session, resident_id, now).features["video"]
    if not feature.allowed:
        raise CallDenied("FEATURE_LOCKED", "video is locked")
    if (
        starts_at.second
        or starts_at.microsecond
        or starts_at.minute % slot
        or minutes % slot
        or not 0 < minutes <= longest
    ):
        raise CallDenied("BAD_SLOT", f"book in {slot}-minute steps, up to {longest} minutes")
    if not now < starts_at <= now + timedelta(days=cfg["video_booking_days_ahead"]):
        raise CallDenied("BAD_SLOT", "choose a time in the next few days")
    end = starts_at + timedelta(minutes=minutes)
    for other in session.execute(
        select(VideoBooking).where(
            VideoBooking.resident_id == resident_id, VideoBooking.status == "scheduled"
        )
    ).scalars():
        if starts_at < other.starts_at + timedelta(minutes=other.minutes) and other.starts_at < end:
            raise CallDenied("SLOT_TAKEN", "you already have a call at that time")
    if not privileged:  # attorney video is not metered, like attorney calls
        used, booked = _week_seconds(session, resident_id, starts_at)
        if used + (booked + minutes) * 60 > feature.limits["minutes_per_week"] * 60:
            raise CallDenied("LIMIT_REACHED", "not enough video minutes left that week")
    row = VideoBooking(
        resident_id=resident_id,
        contact_id=contact_id,
        starts_at=starts_at,
        minutes=minutes,
        created_at=now,
    )
    session.add(row)
    session.flush()
    return row


def cancel(session: Session, resident_id: int, booking_id: int, now: datetime) -> VideoBooking:
    b = session.get(VideoBooking, booking_id)
    if b is None or b.resident_id != resident_id:
        raise CallDenied("NOT_FOUND", "booking not found")
    if b.status != "scheduled":
        raise CallDenied("NOT_SCHEDULED", "this call can no longer be cancelled")
    b.status = "cancelled"
    return b


def upcoming(session: Session, resident_id: int, now: datetime) -> list[VideoBooking]:
    expire(session, resident_id, now)
    return list(
        session.execute(
            select(VideoBooking)
            .where(VideoBooking.resident_id == resident_id, VideoBooking.status == "scheduled")
            .order_by(VideoBooking.starts_at)
        ).scalars()
    )


def start_booked(session: Session, resident_id: int, booking_id: int, now: datetime):
    """Starts the call for a booking, from a few minutes before its slot until the slot ends."""
    early = _cfg(session)["video_start_early_minutes"]
    b = session.execute(
        select(VideoBooking).where(VideoBooking.id == booking_id).with_for_update()
    ).scalar()
    if b is None or b.resident_id != resident_id:
        raise CallDenied("NOT_FOUND", "booking not found")
    if b.status != "scheduled":
        raise CallDenied("NOT_SCHEDULED", "this call can no longer be started")
    if now < b.starts_at - timedelta(minutes=early):
        raise CallDenied("TOO_EARLY", "it is not time for this call yet")
    if now > b.starts_at + timedelta(minutes=b.minutes):
        b.status = "missed"
        raise CallDenied("MISSED", "this call's time has passed")
    record = start_call(session, resident_id, b.contact_id, now, medium="video", booking=b)
    b.status, b.call_id = "started", record.id
    return record
