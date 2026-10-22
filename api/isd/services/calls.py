"""Calls: approved contacts, per-tier limits, monitored vs privileged handling."""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from isd.engine.authority import Evidence
from isd.engine.calls import CallDenied, effective_seconds, plan_call
from isd.interfaces.telephony import CallHandle, PrivilegedCommunicationError, TelephonyService
from isd.models import CallRecord, Contact
from isd.providers import get_telephony
from isd.services.audit import SYSTEM, Actor, append_audit
from isd.services.config_store import get_current
from isd.services.entitlement_service import get_entitlements
from isd.services.usage import call_seconds_today, video_seconds_this_week


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
    session: Session, resident_id: int, now: datetime, telephony: TelephonyService | None = None
) -> None:
    """Close calls that ran past their cap (e.g. the device lost power mid-call)."""
    tel = telephony or get_telephony()
    open_calls = session.execute(
        select(CallRecord)
        .where(CallRecord.resident_id == resident_id, CallRecord.status == "active")
        .with_for_update()
    ).scalars()
    for c in open_calls:
        if now >= c.started_at + timedelta(seconds=c.max_seconds):
            _finish(c, c.started_at + timedelta(seconds=c.max_seconds), "timed_out", tel)


def _finish(c: CallRecord, ended: datetime, status: str, tel: TelephonyService) -> None:
    handle = CallHandle(c.provider_ref, c.privileged)
    c.monitor_ref = tel.end_call(handle)  # None for privileged calls, by construction
    c.ended_at, c.status = ended, status
    c.duration_seconds = effective_seconds(c.started_at, ended, c.max_seconds)


def start_call(
    session: Session,
    resident_id: int,
    contact_id: int,
    now: datetime,
    telephony: TelephonyService | None = None,
    medium: str = "voice",
) -> CallRecord:
    tel = telephony or get_telephony()
    contact = session.get(Contact, contact_id)
    if (
        contact is None
        or contact.resident_id != resident_id
        or not contact.approved
        or not contact.phone_ref
    ):
        raise CallDenied("CONTACT_UNAVAILABLE", "contact not available")
    privileged = contact.type in privileged_types(session)
    if medium == "video" and privileged:
        # Attorney access stays on the phone, where the privilege guard is. No video stub for it.
        raise CallDenied("VIDEO_NOT_AVAILABLE", "use a phone call to reach your attorney")
    # No-contact orders block regular contacts. Attorney access is baseline, so it is never blocked.
    if contact.blocked and not privileged:
        raise CallDenied("CONTACT_UNAVAILABLE", "contact not available")

    settle_open_calls(session, resident_id, now, tel)
    if session.execute(
        select(CallRecord.id).where(
            CallRecord.resident_id == resident_id, CallRecord.status == "active"
        )
    ).first():
        raise CallDenied("CALL_IN_PROGRESS", "a call is already in progress")

    ent = get_entitlements(session, resident_id, now)
    if medium == "video":
        feature, limit_key = ent.features["video"], "minutes_per_week"
        used = video_seconds_this_week(session, resident_id, now)
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

    handle = tel.place_call(contact.phone_ref, privileged=privileged, max_seconds=plan.max_seconds)
    record = CallRecord(
        resident_id=resident_id,
        contact_id=contact.id,
        contact_type=contact.type,
        privileged=plan.privileged,
        monitored=plan.monitored,
        provider_ref=handle.provider_ref,
        started_at=now,
        max_seconds=plan.max_seconds,
        status="active",
        medium=medium,
    )
    session.add(record)
    session.flush()
    return record


def end_call(
    session: Session,
    resident_id: int,
    call_id: int,
    now: datetime,
    telephony: TelephonyService | None = None,
) -> CallRecord:
    tel = telephony or get_telephony()
    c = session.execute(
        select(CallRecord).where(CallRecord.id == call_id).with_for_update()
    ).scalar()
    if c is None or c.resident_id != resident_id:
        raise CallDenied("NOT_FOUND", "call not found")
    if c.status != "active":
        return c  # ending twice is harmless
    over = now >= c.started_at + timedelta(seconds=c.max_seconds)
    ended = c.started_at + timedelta(seconds=c.max_seconds) if over else now
    _finish(c, ended, "timed_out" if over else "completed", tel)
    return c


def fetch_recording(
    session: Session,
    actor: Actor,
    call_id: int,
    telephony: TelephonyService | None = None,
) -> bytes:
    """Staff access to a monitored call. Always audit-logged; never works for attorney calls."""
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
    append_audit(
        session,
        actor,
        "monitoring_access",
        "call",
        call_id,
        "MONITORING_ACCESS",
        payload={"call_id": call_id, "resident_id": c.resident_id},
    )
    return tel.recording(CallHandle(c.provider_ref, False))


def report_video_tamper(
    session: Session,
    resident_id: int,
    call_id: int,
    now: datetime,
    telephony: TelephonyService | None = None,
):
    """The device saw its camera covered during a video call: end the call and raise DEVICE_TAMPER.

    The sanction is system-detected evidence only; a supervisor still has to confirm it. Reporting
    the same call twice does not create a second sanction.
    """
    from sqlalchemy import select as _select

    from isd.models import Sanction
    from isd.services.sanctions import issue_sanction

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
    end_call(session, resident_id, call_id, now, telephony)
    return issue_sanction(
        session, SYSTEM, resident_id, "DEVICE_TAMPER", now, Evidence("system_event", ref=ref)
    )
