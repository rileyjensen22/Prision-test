"""Contacts: residents request, staff approve. No-contact orders spare only the baseline."""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from isd.engine.contacts import ContactInvalid, can_review, clean_request
from isd.models import Contact, VideoBooking
from isd.providers import get_verifier
from isd.services.audit import Actor, append_audit
from isd.services.config_store import get_current

RESIDENT = Actor(None, "resident")


def _compliance(session: Session) -> dict:
    return get_current(session, "compliance").payload


def request_contact(
    session: Session, resident_id: int, name: str, kind: str, phone: str, now: datetime
) -> Contact:
    name, kind, phone = clean_request(name, kind, phone)
    cfg = _compliance(session)
    counts = dict(
        session.execute(
            select(Contact.status, func.count())
            .where(Contact.resident_id == resident_id)
            .group_by(Contact.status)
        ).all()
    )
    if counts.get("pending", 0) >= cfg["contact_max_pending"]:
        raise ContactInvalid("TOO_MANY_PENDING", "wait for your open requests to be reviewed")
    if counts.get("approved", 0) >= cfg["contact_max_approved"]:
        raise ContactInvalid("CONTACT_LIST_FULL", "your contact list is full")
    same = session.execute(
        select(Contact.id).where(
            Contact.resident_id == resident_id,
            Contact.phone_ref == phone,
            Contact.status != "rejected",
        )
    ).first()
    if same:
        raise ContactInvalid("DUPLICATE", "that number is already on your list")
    row = Contact(
        resident_id=resident_id,
        name=name,
        type=kind,
        phone_ref=phone,
        approved=False,
        status="pending",
        requested_by="resident",
        requested_at=now,
    )
    session.add(row)
    session.flush()
    append_audit(
        session,
        RESIDENT,
        "contact_requested",
        "contact",
        row.id,
        "CONTACT_REQUEST",
        payload={"resident_id": resident_id, "type": kind},
    )
    return row


def pending(session: Session) -> list[dict]:
    rows = session.execute(
        select(Contact)
        .where(Contact.status == "pending")
        .order_by(Contact.requested_at, Contact.id)
    ).scalars()
    return [
        {
            "id": c.id,
            "resident_id": c.resident_id,
            "name": c.name,
            "type": c.type,
            "phone": c.phone_ref,
            "requested_at": c.requested_at.isoformat() if c.requested_at else None,
            "verification": get_verifier().verify(c.type, c.phone_ref or ""),
        }
        for c in rows
    ]


class ContactReviewError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def review_contact(
    session: Session, actor: Actor, contact_id: int, approve: bool, note: str, now: datetime
) -> Contact:
    c = session.execute(select(Contact).where(Contact.id == contact_id).with_for_update()).scalar()
    if c is None:
        raise ContactReviewError("NOT_FOUND", "contact not found")
    if c.status != "pending":
        raise ContactReviewError("NOT_PENDING", "this request was already reviewed")
    if not can_review(actor.role, c.type):
        raise ContactReviewError("NEEDS_SUPERVISOR", "attorney contacts need a supervisor")
    note = note.strip()
    if not approve and len(note) < 3:
        raise ContactReviewError("REASON_REQUIRED", "say why the request is refused")
    c.status = "approved" if approve else "rejected"
    c.approved = approve
    c.verification = get_verifier().verify(c.type, c.phone_ref or "")
    c.reviewed_by, c.reviewed_at, c.review_note = actor.id, now, note or None
    append_audit(
        session,
        actor,
        "contact_approved" if approve else "contact_rejected",
        "contact",
        c.id,
        "CONTACT_REVIEW",
        payload={
            "resident_id": c.resident_id,
            "type": c.type,
            "verification": c.verification,
            "note": note,
        },
    )
    return c


def set_blocked(
    session: Session, actor: Actor, contact_id: int, blocked: bool, reason: str, now: datetime
) -> Contact:
    """A no-contact order. It never applies to attorney contacts (protected baseline)."""
    c = session.get(Contact, contact_id)
    if c is None:
        raise ContactReviewError("NOT_FOUND", "contact not found")
    if len(reason.strip()) < 5:
        raise ContactReviewError("REASON_REQUIRED", "give a reason")
    if c.type == "attorney":
        raise ContactReviewError("PROTECTED", "attorney contacts cannot be blocked")
    c.blocked = blocked
    if blocked:  # scheduled video calls with a blocked contact are cancelled
        for b in session.execute(
            select(VideoBooking).where(
                VideoBooking.contact_id == c.id, VideoBooking.status == "scheduled"
            )
        ).scalars():
            b.status = "cancelled"
    append_audit(
        session,
        actor,
        "contact_blocked" if blocked else "contact_unblocked",
        "contact",
        c.id,
        "NO_CONTACT_ORDER",
        payload={"resident_id": c.resident_id, "reason": reason.strip()},
    )
    return c


def all_for_resident(session: Session, resident_id: int) -> list[Contact]:
    return list(
        session.execute(
            select(Contact).where(Contact.resident_id == resident_id).order_by(Contact.id)
        ).scalars()
    )
