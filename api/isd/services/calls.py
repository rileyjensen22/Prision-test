"""Calls: approved contacts, per-tier limits, monitored vs privileged handling."""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from isd.engine.authority import Evidence
from isd.engine.calls import CallDenied, effective_seconds, plan_call
from isd.interfaces.telephony import CallHandle, PrivilegedCommunicationError, TelephonyService
from isd.interfaces.video import VideoHandle, VideoService
from isd.models import CallRecord, Contact
from isd.providers import get_telephony, get_video
from isd.services.audit import SYSTEM, Actor, append_audit
from isd.services.config_store import get_current
from isd.services.entitlement_service import get_entitlements
from isd.services.usage import call_seconds_today, video_seconds_today


def privileged_types(session: Session) -> set[str]:
    return set(get_current(session, "compliance").payload["privileged_contact_types"])


def list_contacts(session: Session, resident_id: int) -> list[Contact]:
    return list(
        session.execute(
            select(Contact)
            .where(Contact.resident_id == resident_id, Contact.approved.is_(True))
            .order_by(Contact.id)
        ).scalars()
    )


def settle_open_calls(
    session: Session,
    resident_id: int,
    now: datetime,
    telephony: TelephonyService | None = None,
    video: VideoService | None = None,
) -> None:
    """Close calls that ran past their cap (e.g. the device lost power mid-call)."""
    tel, vid = telephony or get_telephony(), video or get_video()
    open_calls = session.execute(
        select(CallRecord)
        .where(CallRecord.resident_id == resident_id, CallRecord.status == "active")
        .with_for_update()
    ).scalars()
    for c in open_calls:
        if now >= c.started_at + timedelta(seconds=c.max_seconds):
            _finish(c, c.started_at + timedelta(seconds=c.max_seconds), "timed_out", tel, vid)


def _finish(
    c: CallRecord, ended: datetime, status: str, tel: TelephonyService, vid: VideoService
) -> None:
    if c.medium == "video":
        c.monitor_ref = vid.end(VideoHandle(c.provider_ref, c.privileged, {}))
    else:
        c.monitor_ref = tel.end_call(CallHandle(c.provider_ref, c.privileged))
    # monitor_ref is None for privileged calls, by construction
    c.ended_at, c.status = ended, status
    c.duration_seconds = effective_seconds(c.started_at, ended, c.max_seconds)


def _recording_enabled(session: Session) -> bool:
    return bool(get_current(session, "compliance").payload.get("video_recording_enabled", False))


def start_call(
    session: Session,
    resident_id: int,
    contact_id: int,
    now: datetime,
    telephony: TelephonyService | None = None,
    medium: str = "voice",
    video: VideoService | None = None,
    booking=None,
):
    """Starts a voice or video call. `booking` (a VideoBooking) limits a video call to its slot.

    Returns the CallRecord; for video the provider's connection info is on `record.connection`
    (not stored).
    """
    tel, vid = telephony or get_telephony(), video or get_video()
    contact = session.get(Contact, contact_id)
    if (
        contact is None
        or contact.resident_id != resident_id
        or not contact.approved
        or not contact.phone_ref
    ):
        raise CallDenied("CONTACT_UNAVAILABLE", "contact not available")
    privileged = contact.type in privileged_types(session)
    # No-contact orders block regular contacts. Attorney access is baseline, so it is never blocked.
    if contact.blocked and not privileged:
        raise CallDenied("CONTACT_UNAVAILABLE", "contact not available")

    settle_open_calls(session, resident_id, now, tel, vid)
    if privileged:  # attorney access is baseline: it ends a stale family call rather than wait
        for stale in session.execute(
            select(CallRecord)
            .where(
                CallRecord.resident_id == resident_id,
                CallRecord.status == "active",
                CallRecord.privileged.is_(False),
            )
            .with_for_update()
        ).scalars():
            _finish(stale, now, "completed", tel, vid)
    if session.execute(
        select(CallRecord.id).where(
            CallRecord.resident_id == resident_id, CallRecord.status == "active"
        )
    ).first():
        raise CallDenied("CALL_IN_PROGRESS", "a call is already in progress")

    ent = get_entitlements(session, resident_id, now)
    if medium == "video":
        feature, limit_key = ent.features["video"], "minutes_per_week"
        used = video_seconds_today(session, resident_id, now)
        if not privileged:  # minutes booked for other calls are spoken for
            used += reserved_video_seconds(session, resident_id, now, except_booking=booking)
        if privileged and not feature.allowed:
            # attorney access stays open by phone; video is an extra and follows the video lock
            raise CallDenied("FEATURE_LOCKED", "video is locked; call your attorney by phone")
    else:
        feature, limit_key = ent.features["calls"], "minutes_per_day"
        used = call_seconds_today(session, resident_id, now)
    plan = plan_call(
        privileged=privileged,
        allowed=feature.allowed,
        limit_minutes=feature.limits.get(limit_key),
        used_seconds=used,
    )
    if privileged and not ent.allowed("attorney_calls"):  # cannot happen: baseline
        raise CallDenied("FEATURE_LOCKED", "attorney calls unavailable")
    max_seconds = plan.max_seconds
    if booking is not None:
        max_seconds = min(max_seconds, booking.minutes * 60)

    connection: dict = {}
    if medium == "video":
        handle = vid.place(
            contact.phone_ref,
            privileged=privileged,
            record=_recording_enabled(session),
            max_seconds=max_seconds,
        )
        provider_ref, connection = handle.provider_ref, handle.connection
    else:
        provider_ref = tel.place_call(
            contact.phone_ref, privileged=privileged, max_seconds=max_seconds
        ).provider_ref
    record = CallRecord(
        resident_id=resident_id,
        contact_id=contact.id,
        contact_type=contact.type,
        privileged=plan.privileged,
        monitored=plan.monitored,
        provider_ref=provider_ref,
        started_at=now,
        max_seconds=max_seconds,
        status="active",
        medium=medium,
    )
    session.add(record)
    session.flush()
    record.connection = connection  # type: ignore[attr-defined]
    return record


def end_call(
    session: Session,
    resident_id: int,
    call_id: int,
    now: datetime,
    telephony: TelephonyService | None = None,
    video: VideoService | None = None,
) -> CallRecord:
    tel, vid = telephony or get_telephony(), video or get_video()
    c = session.execute(
        select(CallRecord).where(CallRecord.id == call_id).with_for_update()
    ).scalar()
    if c is None or c.resident_id != resident_id:
        raise CallDenied("NOT_FOUND", "call not found")
    if c.status != "active":
        return c  # ending twice is harmless
    over = now >= c.started_at + timedelta(seconds=c.max_seconds)
    ended = c.started_at + timedelta(seconds=c.max_seconds) if over else now
    _finish(c, ended, "timed_out" if over else "completed", tel, vid)
    return c


MIN_REASON = 5


def fetch_recording(
    session: Session,
    actor: Actor,
    call_id: int,
    reason: str,
    telephony: TelephonyService | None = None,
) -> bytes:
    """Staff access to a monitored call. Needs a stated reason, is audit-logged, and never works
    for attorney calls (invariants 6 and 16)."""
    tel = telephony or get_telephony()
    c = session.get(CallRecord, call_id)
    if c is None:
        raise LookupError("call not found")
    if actor.role not in ("supervisor", "admin"):
        raise PermissionError("role cannot access call content")
    if c.privileged:
        append_audit(
            session,
            actor,
            "monitoring_denied",
            "call",
            call_id,
            "PRIVILEGED_DENIED",
            payload={"call_id": call_id},
        )
        raise PrivilegedCommunicationError("privileged calls have no recording")
    if len(reason.strip()) < MIN_REASON:
        raise PermissionError("state why you are reviewing this call")
    if c.medium == "video":
        raise LookupError("video recordings are reviewed through the provider, not this app")
    append_audit(
        session,
        actor,
        "monitoring_access",
        "call",
        call_id,
        "MONITORING_ACCESS",
        payload={"call_id": call_id, "resident_id": c.resident_id, "reason": reason.strip()},
    )
    return tel.recording(CallHandle(c.provider_ref, False))


# The device reports only a derived signal about its own camera, never an image (invariant 14).
TAMPER_SIGNALS = ("dark", "flat")


def report_video_tamper(
    session: Session,
    resident_id: int,
    call_id: int,
    now: datetime,
    signal: str = "dark",
    telephony: TelephonyService | None = None,
    video: VideoService | None = None,
):
    """The device saw its camera covered during a video call: end the call and raise DEVICE_TAMPER.

    Only an active video call can report this. The sanction is system-detected evidence only; a
    supervisor still has to confirm it. Reporting the same call twice does not create a second
    sanction. Nothing about the picture is kept: only that the device reported `signal`.
    """
    from sqlalchemy import select as _select

    from isd.models import Sanction
    from isd.services.sanctions import issue_sanction

    if signal not in TAMPER_SIGNALS:
        raise CallDenied("BAD_SIGNAL", "unknown tamper signal")
    c = session.execute(
        _select(CallRecord).where(CallRecord.id == call_id).with_for_update()
    ).scalar()
    if c is None or c.resident_id != resident_id or c.medium != "video":
        raise CallDenied("NOT_FOUND", "video call not found")
    ref = f"video-call-{c.id}"
    existing = session.execute(_select(Sanction).where(Sanction.evidence_ref == ref)).scalar()
    if existing:
        return existing
    if c.status != "active":
        raise CallDenied("NOT_ACTIVE", "tamper is only detected during an active call")
    end_call(session, resident_id, call_id, now, telephony, video)
    return issue_sanction(
        session, SYSTEM, resident_id, "DEVICE_TAMPER", now, Evidence("system_event", ref=ref)
    )


def reserved_video_seconds(session: Session, resident_id: int, now: datetime, except_booking=None):
    from isd.services.video_bookings import reserved_seconds

    return reserved_seconds(session, resident_id, now, except_booking)


def purge_expired_recordings(session: Session, now: datetime, video: VideoService | None = None):
    """Deletes provider-side video recordings past `recording_retention_days` (unset keeps them)."""
    days = get_current(session, "compliance").payload.get("recording_retention_days")
    if not days:
        return 0
    vid = video or get_video()
    purged = 0
    old = session.execute(
        select(CallRecord)
        .where(
            CallRecord.medium == "video",
            CallRecord.monitor_ref.is_not(None),
            CallRecord.recording_purged_at.is_(None),
            CallRecord.ended_at < now - timedelta(days=days),
        )
        .with_for_update()
    ).scalars()
    for c in old:
        vid.purge(c.provider_ref)
        c.monitor_ref, c.recording_purged_at = None, now
        append_audit(
            session,
            SYSTEM,
            "recording_purged",
            "call",
            c.id,
            "RETENTION",
            payload={"call_id": c.id, "retention_days": days},
        )
        purged += 1
    return purged
