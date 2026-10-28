"""Retention: delete old operational records on the schedule `compliance.yaml` sets.

Every period is unset (`null`) by default, which keeps everything. A number of days turns that
rule on. The job deletes only operational records that are not the system of record for a
decision or for money. It never touches the tables in PROTECTED (the audit log, config history,
ledgers, points, sanctions, appeals and the like): those are append-only in the database, and this
module refuses to be configured to include them. What was deleted is recorded as counts only.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from isd.models import (
    CallRecord,
    DeviceCommand,
    DevicePairing,
    Message,
    MessageFlag,
    QuizAttempt,
    ReadingLog,
    StaffRequest,
    VideoBooking,
)
from isd.services.audit import SYSTEM, Actor, append_audit
from isd.services.config_store import get_current

# Tables that are never deleted from by this job, whatever the configuration says.
PROTECTED = frozenset(
    {
        "audit_log",
        "config_versions",
        "trust_ledger",
        "earnings_ledger",
        "out_of_cell_log",
        "out_of_cell_events",
        "reentry_events",
        "outcome_records",
        "outcome_import_batches",
        "point_events",
        "tier_history",
        "sanctions",
        "appeals",
        "welfare_flags",
        "welfare_acks",
        "reconciliation_runs",
        "keep_separate",
        "mirror_sessions",
        "work_log",
        "certificates",
    }
)


class RetentionConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Rule:
    config_key: str
    table: str
    what: str


RULES = (
    Rule("message_retention_days", "messages", "text messages (and their flags)"),
    Rule("call_metadata_retention_days", "call_records", "call and video call records"),
    Rule("staff_request_retention_days", "staff_requests", "resident requests to staff"),
    Rule("reading_log_retention_days", "reading_log", "reading history"),
    Rule("quiz_attempt_retention_days", "quiz_attempts", "quiz attempts"),
    Rule("device_record_retention_days", "device_pairings", "device pairing codes and commands"),
)
assert not {r.table for r in RULES} & PROTECTED


def _days(payload: dict, key: str) -> int | None:
    value = payload.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise RetentionConfigError(f"{key} must be a whole number of days, 1 or more, or null")
    return value


def _delete_messages(session: Session, cutoff: datetime) -> int:
    old = select(Message.id).where(Message.created_at < cutoff)
    session.execute(delete(MessageFlag).where(MessageFlag.message_id.in_(old)))
    return session.execute(delete(Message).where(Message.created_at < cutoff)).rowcount


def _delete_calls(session: Session, cutoff: datetime) -> int:
    old = select(CallRecord.id).where(CallRecord.started_at < cutoff, CallRecord.status != "active")
    session.execute(update(VideoBooking).where(VideoBooking.call_id.in_(old)).values(call_id=None))
    return session.execute(
        delete(CallRecord).where(CallRecord.started_at < cutoff, CallRecord.status != "active")
    ).rowcount


def _delete_requests(session: Session, cutoff: datetime) -> int:
    return session.execute(delete(StaffRequest).where(StaffRequest.created_at < cutoff)).rowcount


def _delete_reading(session: Session, cutoff: datetime) -> int:
    return session.execute(delete(ReadingLog).where(ReadingLog.at < cutoff)).rowcount


def _delete_quiz(session: Session, cutoff: datetime) -> int:
    return session.execute(delete(QuizAttempt).where(QuizAttempt.at < cutoff)).rowcount


def _delete_device_records(session: Session, cutoff: datetime) -> int:
    n = session.execute(
        delete(DevicePairing).where(
            DevicePairing.created_at < cutoff,
            (DevicePairing.used_at.is_not(None)) | (DevicePairing.expires_at < cutoff),
        )
    ).rowcount
    n += session.execute(
        delete(DeviceCommand).where(
            DeviceCommand.issued_at < cutoff, DeviceCommand.acked_at.is_not(None)
        )
    ).rowcount
    return n


_RUNNERS = {
    "message_retention_days": _delete_messages,
    "call_metadata_retention_days": _delete_calls,
    "staff_request_retention_days": _delete_requests,
    "reading_log_retention_days": _delete_reading,
    "quiz_attempt_retention_days": _delete_quiz,
    "device_record_retention_days": _delete_device_records,
}


def run(session: Session, now: datetime, actor: Actor = SYSTEM) -> dict[str, int]:
    """Applies every rule that has a period set. Returns rows deleted per rule (only rules that
    ran). Safe to repeat. Writes one audit entry with the counts when anything was deleted."""
    payload = get_current(session, "compliance").payload
    counts: dict[str, int] = {}
    for rule in RULES:
        days = _days(payload, rule.config_key)
        if days is None:
            continue
        counts[rule.config_key] = _RUNNERS[rule.config_key](session, now - timedelta(days=days))
    if any(counts.values()):
        append_audit(
            session,
            actor,
            "retention_run",
            "system",
            "retention",
            reason_code="RETENTION",
            payload={"deleted": {k: v for k, v in counts.items() if v}},
        )
    session.flush()
    return counts
