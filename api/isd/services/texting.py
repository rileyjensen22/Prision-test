"""Texting (stub): monitored, tier-gated, daily limit. Attorney messages are never kept."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from isd.interfaces.messaging import MessagingService
from isd.models import Contact, Message
from isd.providers import get_messaging
from isd.services import monitoring
from isd.services.calls import privileged_types
from isd.services.config_store import get_current
from isd.services.entitlement_service import get_entitlements
from isd.services.usage import messages_sent_today

DEFAULT_MAX_BODY = 500


class TextDenied(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def send_text(
    session: Session,
    resident_id: int,
    contact_id: int,
    body: str,
    now: datetime,
    messaging: MessagingService | None = None,
) -> Message:
    svc = messaging or get_messaging()
    contact = session.get(Contact, contact_id)
    if (
        contact is None
        or contact.resident_id != resident_id
        or not contact.approved
        or not contact.phone_ref
    ):
        raise TextDenied("CONTACT_UNAVAILABLE", "contact not available")
    privileged = contact.type in privileged_types(session)
    if contact.blocked and not privileged:
        raise TextDenied("CONTACT_UNAVAILABLE", "contact not available")
    text = body.strip()
    max_body = get_current(session, "monitoring").payload["text_max_chars"]
    if not 1 <= len(text) <= max_body:
        raise TextDenied("BAD_MESSAGE", f"messages must be 1 to {max_body} characters")
    fe = get_entitlements(session, resident_id, now).features["texting"]
    if not fe.allowed:
        raise TextDenied("FEATURE_LOCKED", "texting is locked")
    if messages_sent_today(session, resident_id, now) >= fe.limits["messages_per_day"]:
        raise TextDenied("LIMIT_REACHED", "daily message limit reached")

    sent = svc.send(contact.phone_ref, text, privileged=privileged)
    row = Message(
        resident_id=resident_id,
        contact_id=contact.id,
        direction="out",
        body=None if privileged else text,  # privileged: no content is ever stored
        privileged=privileged,
        monitored=not privileged,
        delivery=sent.delivery,
        created_at=now,
    )
    session.add(row)
    session.flush()
    monitoring.flag_message(session, row, now)  # review items only (invariant 12)
    if sent.reply:  # monitored threads show the (mock) reply
        reply = Message(
            resident_id=resident_id,
            contact_id=contact.id,
            direction="in",
            body=sent.reply,
            privileged=False,
            monitored=True,
            created_at=now,
        )
        session.add(reply)
        session.flush()
        monitoring.flag_message(session, reply, now)
    session.flush()
    return row


def thread(session: Session, resident_id: int, contact_id: int) -> list[Message]:
    return list(
        session.execute(
            select(Message)
            .where(Message.resident_id == resident_id, Message.contact_id == contact_id)
            .order_by(Message.id)
        ).scalars()
    )
