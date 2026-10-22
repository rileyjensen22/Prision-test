"""Staff review of monitored (non-attorney) messages.

Reading a message needs a stated reason and is audit-logged (invariant 16). Attorney messages are
never listed and never readable by any role (invariant 6). A keyword flag is a review item only:
nothing in this module creates a sanction (invariant 12).
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from isd.engine.monitoring import match_rules
from isd.models import Contact, Message, MessageFlag, Resident
from isd.services.audit import Actor, append_audit
from isd.services.config_store import get_current

READER_ROLES = ("supervisor", "admin", "auditor")  # read monitored content, with a reason
REVIEWER_ROLES = ("supervisor", "admin")  # record the outcome of a flag
MIN_REASON = 5


class MonitoringDenied(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def flag_message(session: Session, message: Message, now: datetime) -> list[MessageFlag]:
    """Called when a monitored message is stored. Creates review items; nothing else."""
    if message.privileged or not message.monitored or not message.body:
        return []
    rules = get_current(session, "monitoring").payload["rules"]
    flags = []
    for rule in match_rules(message.body, rules):
        flag = MessageFlag(
            message_id=message.id, rule_id=rule["id"], label=rule["label"], created_at=now
        )
        session.add(flag)
        flags.append(flag)
    session.flush()
    return flags


def queue(session: Session, flagged_only: bool = False, limit: int = 100) -> list[dict]:
    """Metadata only: who, when, which rules matched. Never the text."""
    q = (
        select(Message, Contact.type, Resident.code)
        .join(Contact, Contact.id == Message.contact_id)
        .join(Resident, Resident.id == Message.resident_id)
        .where(Message.monitored.is_(True), Message.privileged.is_(False))
        .order_by(Message.id.desc())
    )
    rows = session.execute(q.limit(500)).all()
    flags: dict[int, list[MessageFlag]] = {}
    ids = [m.id for m, _, _ in rows]
    if ids:
        for f in session.execute(
            select(MessageFlag).where(MessageFlag.message_id.in_(ids))
        ).scalars():
            flags.setdefault(f.message_id, []).append(f)
    out = []
    for m, ctype, code in rows:
        fl = flags.get(m.id, [])
        if flagged_only and not any(f.status != "reviewed" for f in fl):
            continue
        out.append(
            {
                "message_id": m.id,
                "resident_id": m.resident_id,
                "resident": code,
                "direction": m.direction,
                "contact_type": ctype,
                "at": m.created_at.isoformat(),
                "flags": [
                    {"id": f.id, "label": f.label, "status": f.status, "rule_id": f.rule_id}
                    for f in fl
                ],
            }
        )
    out.sort(key=lambda r: not any(f["status"] == "open" for f in r["flags"]))  # open flags first
    return out[:limit]


def read_message(
    session: Session, actor: Actor, message_id: int, reason: str, now: datetime
) -> dict:
    if actor.role not in READER_ROLES:
        raise MonitoringDenied("FORBIDDEN", "this role cannot read monitored messages")
    if len(reason.strip()) < MIN_REASON:
        raise MonitoringDenied("REASON_REQUIRED", "state why you are reading this message")
    m = session.get(Message, message_id)
    if m is None or not m.monitored:
        # unknown ids and privileged messages look the same: nothing is revealed about either
        raise MonitoringDenied("NOT_FOUND", "message not found")
    if m.privileged or m.body is None:
        raise MonitoringDenied("NOT_FOUND", "message not found")
    append_audit(
        session,
        actor,
        "monitoring_access",
        "message",
        m.id,
        "MESSAGE_READ",
        payload={"reason": reason.strip(), "resident_id": m.resident_id},  # never the text
    )
    return {
        "message_id": m.id,
        "resident_id": m.resident_id,
        "direction": m.direction,
        "body": m.body,
        "at": m.created_at.isoformat(),
    }


def review_flag(
    session: Session, actor: Actor, flag_id: int, outcome: str, reason: str, now: datetime
) -> MessageFlag:
    """Records what a person decided. 'referred' hands it to a supervisor; neither sanctions."""
    if actor.role not in REVIEWER_ROLES:
        raise MonitoringDenied("FORBIDDEN", "this role cannot review flags")
    if outcome not in ("no_action", "referred"):
        raise MonitoringDenied("BAD_OUTCOME", "outcome must be no_action or referred")
    if len(reason.strip()) < MIN_REASON:
        raise MonitoringDenied("REASON_REQUIRED", "state the reason for this outcome")
    f = session.get(MessageFlag, flag_id)
    if f is None:
        raise MonitoringDenied("NOT_FOUND", "flag not found")
    f.status = "reviewed" if outcome == "no_action" else "referred"
    f.reviewed_by, f.reviewed_at, f.review_reason = actor.id, now, reason.strip()
    append_audit(
        session,
        actor,
        "flag_reviewed",
        "message_flag",
        f.id,
        "FLAG_REVIEW",
        payload={"outcome": outcome, "reason": reason.strip(), "rule_id": f.rule_id},
    )
    return f
