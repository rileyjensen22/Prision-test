"""Phase 1 data model. Business rules live in isd.engine, not here."""

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from isd.crypto import EncryptedText, blind_index

ROLES = ("officer", "supervisor", "admin", "auditor")
CONTACT_TYPES = ("family", "friend", "attorney")
SANCTION_STATUSES = ("pending", "active", "rejected", "expired", "overturned")
APPEAL_STATUSES = ("open", "upheld", "overturned")


class Base(DeclarativeBase):
    pass


def _now() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


class Staff(Base):
    __tablename__ = "staff"
    __table_args__ = (CheckConstraint(f"role IN {ROLES}", name="ck_staff_role"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    role: Mapped[str] = mapped_column(String(16))
    password_hash: Mapped[str] = mapped_column(String(255))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = _now()
    # Sign-in security (Phase 18). The TOTP secret is stored encrypted; recovery codes are stored
    # only as hashes and each works once.
    mfa_secret: Mapped[str | None] = mapped_column(EncryptedText("staff.mfa_secret"), nullable=True)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    mfa_recovery_hashes: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    mfa_last_step: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    password_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ConfigVersion(Base):
    """Insert-only history of each config section (invariant 9). Current = highest version."""

    __tablename__ = "config_versions"
    __table_args__ = (UniqueConstraint("name", "version", name="uq_config_name_version"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    reason: Mapped[str] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("staff.id"), nullable=True)
    created_at: Mapped[datetime] = _now()


class Resident(Base):
    __tablename__ = "residents"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    display_name: Mapped[str] = mapped_column(String(128))
    language: Mapped[str] = mapped_column(String(8), default="en")
    text_size: Mapped[str] = mapped_column(String(16), default="normal")
    reading_level: Mapped[str] = mapped_column(String(16), default="standard")
    captions: Mapped[bool] = mapped_column(Boolean, default=False)
    prior_returns: Mapped[int] = mapped_column(Integer, default=0)
    prior_returns_source: Mapped[str | None] = mapped_column(String(128), nullable=True)
    release_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = _now()
    # Set when staff vacate the resident (released or moved out). The record stays: history,
    # ledgers and the audit log are never deleted.
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Staff switch for human chess: None follows the unit and facility setting.
    chess_human: Mapped[bool | None] = mapped_column(Boolean, nullable=True)


class Cell(Base):
    __tablename__ = "cells"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    unit: Mapped[str] = mapped_column(String(16), default="A", server_default="A")
    # The line the cell is on. Chess never pairs two residents on the same line. Phase 20 derives
    # it from the facility model; until then staff set it at intake.
    line_code: Mapped[str | None] = mapped_column(String(16), nullable=True)


class Device(Base):
    __tablename__ = "devices"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    token_hash: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    current_screen: Mapped[str | None] = mapped_column(String(100), nullable=True)
    screen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    health: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # last heartbeat body
    health_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DeviceAssignment(Base):
    """Device -> cell -> resident. Identity source for the kiosk; changes are audit-logged."""

    __tablename__ = "device_assignments"
    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"))
    cell_id: Mapped[int] = mapped_column(ForeignKey("cells.id"))
    resident_id: Mapped[int] = mapped_column(ForeignKey("residents.id"))
    assigned_by: Mapped[int | None] = mapped_column(ForeignKey("staff.id"), nullable=True)
    assigned_at: Mapped[datetime] = _now()
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Contact(Base):
    __tablename__ = "contacts"
    __table_args__ = (
        CheckConstraint(f"type IN {CONTACT_TYPES}", name="ck_contact_type"),
        CheckConstraint("status IN ('pending', 'approved', 'rejected')", name="ck_contact_status"),
        CheckConstraint("approved = (status = 'approved')", name="ck_contact_approved_matches"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    resident_id: Mapped[int] = mapped_column(ForeignKey("residents.id"))
    name: Mapped[str] = mapped_column(String(128))
    type: Mapped[str] = mapped_column(String(16))
    approved: Mapped[bool] = mapped_column(Boolean, default=True)  # always status == 'approved'
    status: Mapped[str] = mapped_column(String(10), default="approved", server_default="approved")
    requested_by: Mapped[str] = mapped_column(String(8), default="staff", server_default="staff")
    blocked: Mapped[bool] = mapped_column(Boolean, default=False)  # no-contact order
    # Synthetic number, stored encrypted; `phone_hash` is a keyed hash for duplicate checks.
    phone_ref: Mapped[str | None] = mapped_column(
        EncryptedText("contacts.phone_ref"), nullable=True
    )
    phone_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    verification: Mapped[str | None] = mapped_column(String(32), nullable=True)
    requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("staff.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class PointEvent(Base):
    __tablename__ = "point_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    resident_id: Mapped[int] = mapped_column(ForeignKey("residents.id"), index=True)
    kind: Mapped[str] = mapped_column(String(64))
    points: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(16))  # system | staff
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("staff.id"), nullable=True)
    created_at: Mapped[datetime] = _now()
    ref_sanction_id: Mapped[int | None] = mapped_column(ForeignKey("sanctions.id"), nullable=True)


class Sanction(Base):
    __tablename__ = "sanctions"
    __table_args__ = (
        CheckConstraint(f"status IN {SANCTION_STATUSES}", name="ck_sanction_status"),
        CheckConstraint(
            "confirmed_by IS NULL OR confirmed_by <> issued_by", name="ck_issuer_not_confirmer"
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    resident_id: Mapped[int] = mapped_column(ForeignKey("residents.id"), index=True)
    infraction_code: Mapped[str] = mapped_column(String(32))
    scope: Mapped[str] = mapped_column(String(32))
    reason_code: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    issued_by: Mapped[int | None] = mapped_column(ForeignKey("staff.id"), nullable=True)
    issued_at: Mapped[datetime] = _now()
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    confirmed_by: Mapped[int | None] = mapped_column(ForeignKey("staff.id"), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    evidence_type: Mapped[str | None] = mapped_column(String(24), nullable=True)
    evidence_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    evidence_reporter_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id"), nullable=True)
    applied_immediately: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    overturned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Appeal(Base):
    __tablename__ = "appeals"
    __table_args__ = (CheckConstraint(f"status IN {APPEAL_STATUSES}", name="ck_appeal_status"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    sanction_id: Mapped[int] = mapped_column(ForeignKey("sanctions.id"), index=True)
    filed_at: Mapped[datetime] = _now()
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="open")
    reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    outcome_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class TierHistory(Base):
    """Earned-tier changes. Current earned tier = latest row (default 1); drops are rate-limited."""

    __tablename__ = "tier_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    resident_id: Mapped[int] = mapped_column(ForeignKey("residents.id"), index=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    from_tier: Mapped[int] = mapped_column(Integer)
    to_tier: Mapped[int] = mapped_column(Integer)
    points: Mapped[int] = mapped_column(Integer)


class OffenseFlag(Base):
    __tablename__ = "offense_flags"
    id: Mapped[int] = mapped_column(primary_key=True)
    resident_id: Mapped[int] = mapped_column(ForeignKey("residents.id"), index=True)
    offense_category: Mapped[str] = mapped_column(String(64))
    added_by: Mapped[int | None] = mapped_column(ForeignKey("staff.id"), nullable=True)
    added_at: Mapped[datetime] = _now()
    next_review_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditLog(Base):
    """Append-only, hash-chained (invariant 3).

    UPDATE/DELETE are blocked by a trigger and by revoked grants.
    """

    __tablename__ = "audit_log"
    seq: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actor_role: Mapped[str] = mapped_column(String(16))  # includes "system"
    action: Mapped[str] = mapped_column(String(64))
    target_type: Mapped[str] = mapped_column(String(32))
    target_id: Mapped[str] = mapped_column(String(64))
    reason_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ref_seq: Mapped[int | None] = mapped_column(ForeignKey("audit_log.seq"), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))


class StaffRequest(Base):
    """Resident pressed Request staff / medical / mental-health (baseline features)."""

    __tablename__ = "staff_requests"
    __table_args__ = (
        CheckConstraint("kind IN ('staff', 'medical', 'mental_health')", name="ck_request_kind"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    resident_id: Mapped[int] = mapped_column(ForeignKey("residents.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    client_id: Mapped[str] = mapped_column(
        String(64), unique=True
    )  # makes offline replay idempotent
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), default="open")
    handled_by: Mapped[int | None] = mapped_column(ForeignKey("staff.id"), nullable=True)


class CallRecord(Base):
    """Metadata only. Privileged (attorney) calls never carry monitoring data (invariant 6)."""

    __tablename__ = "call_records"
    __table_args__ = (
        CheckConstraint("NOT (privileged AND monitored)", name="ck_privileged_not_monitored"),
        CheckConstraint(
            "NOT (privileged AND monitor_ref IS NOT NULL)", name="ck_privileged_no_monitor_ref"
        ),
        CheckConstraint("status IN ('active', 'completed', 'timed_out')", name="ck_call_status"),
        CheckConstraint("medium IN ('voice', 'video')", name="ck_call_medium"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    resident_id: Mapped[int] = mapped_column(ForeignKey("residents.id"), index=True)
    contact_id: Mapped[int] = mapped_column(ForeignKey("contacts.id"))
    contact_type: Mapped[str] = mapped_column(String(16))
    privileged: Mapped[bool] = mapped_column(Boolean)
    monitored: Mapped[bool] = mapped_column(Boolean)
    monitor_ref: Mapped[str | None] = mapped_column(
        EncryptedText("call_records.monitor_ref"), nullable=True
    )
    provider_ref: Mapped[str] = mapped_column(EncryptedText("call_records.provider_ref"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    max_seconds: Mapped[int] = mapped_column(Integer)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active")
    medium: Mapped[str] = mapped_column(String(8), default="voice", server_default="voice")
    recording_purged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class CourseProgress(Base):
    __tablename__ = "course_progress"
    __table_args__ = (UniqueConstraint("resident_id", "course_code", name="uq_progress"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    resident_id: Mapped[int] = mapped_column(ForeignKey("residents.id"), index=True)
    course_code: Mapped[str] = mapped_column(String(32))
    lessons_done: Mapped[list[str]] = mapped_column(JSONB, default=list)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_lesson: Mapped[str | None] = mapped_column(String(40), nullable=True)  # where to resume
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class QuizSession(Base):
    """One quiz paper: which questions were drawn and in what order their choices were shown.
    The answers stay on the server. A paper is resumable until it expires."""

    __tablename__ = "quiz_sessions"
    __table_args__ = (
        CheckConstraint("status IN ('open', 'submitted', 'expired')", name="ck_quiz_status"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    resident_id: Mapped[int] = mapped_column(ForeignKey("residents.id"), index=True)
    course_code: Mapped[str] = mapped_column(String(32))
    questions: Mapped[list] = mapped_column(JSONB)  # [{"id": ..., "order": [bank choice numbers]}]
    attempt_no: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(10), default="open")
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)


class Certificate(Base):
    """Proof a resident finished a course. One per resident and course; never edited."""

    __tablename__ = "certificates"
    __table_args__ = (UniqueConstraint("resident_id", "course_code", name="uq_certificate"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    serial: Mapped[str] = mapped_column(String(32), unique=True)
    resident_id: Mapped[int] = mapped_column(ForeignKey("residents.id"), index=True)
    course_code: Mapped[str] = mapped_column(String(32))
    title: Mapped[dict] = mapped_column(JSONB)  # the course title when it was earned
    level: Mapped[str] = mapped_column(String(10))
    correct: Mapped[int] = mapped_column(Integer)
    total: Mapped[int] = mapped_column(Integer)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"
    id: Mapped[int] = mapped_column(primary_key=True)
    resident_id: Mapped[int] = mapped_column(ForeignKey("residents.id"), index=True)
    course_code: Mapped[str] = mapped_column(String(32))
    correct: Mapped[int] = mapped_column(Integer)
    total: Mapped[int] = mapped_column(Integer)
    passed: Mapped[bool] = mapped_column(Boolean)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CommissaryOrder(Base):
    __tablename__ = "commissary_orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    resident_id: Mapped[int] = mapped_column(ForeignKey("residents.id"), index=True)
    client_id: Mapped[str] = mapped_column(String(64), unique=True)
    total_cents: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CommissaryOrderLine(Base):
    __tablename__ = "commissary_order_lines"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("commissary_orders.id"), index=True)
    item_code: Mapped[str] = mapped_column(String(32))
    qty: Mapped[int] = mapped_column(Integer)
    unit_price_cents: Mapped[int] = mapped_column(Integer)


class TrustLedger(Base):
    """Append-only trust-account ledger (UPDATE/DELETE blocked like the audit log)."""

    __tablename__ = "trust_ledger"
    __table_args__ = (
        CheckConstraint(
            "entry_type IN ('deposit', 'purchase', 'refund', 'adjustment', 'job_payout')",
            name="ck_ledger_type",
        ),
        CheckConstraint("amount_cents <> 0", name="ck_ledger_nonzero"),
        CheckConstraint("balance_after_cents >= 0", name="ck_ledger_no_overdraft"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    resident_id: Mapped[int] = mapped_column(ForeignKey("residents.id"), index=True)
    entry_type: Mapped[str] = mapped_column(String(16))
    amount_cents: Mapped[int] = mapped_column(Integer)  # signed
    balance_after_cents: Mapped[int] = mapped_column(Integer)
    ref: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("commissary_orders.id"), nullable=True)
    memo: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("staff.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class MirrorSession(Base):
    """A staff member watching a device's screen. Every session is logged (CLAUDE.md 9.1)."""

    __tablename__ = "mirror_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    staff_id: Mapped[int] = mapped_column(ForeignKey("staff.id"), index=True)
    resident_id: Mapped[int] = mapped_column(ForeignKey("residents.id"), index=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"))
    reason: Mapped[str] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_reason: Mapped[str | None] = mapped_column(String(16), nullable=True)  # manual|timeout|idle
    frames_served: Mapped[int] = mapped_column(Integer, default=0)


class OutOfCellLog(Base):
    """Facility-entered minutes out of the cell per day. Append-only: a correction is a new row."""

    __tablename__ = "out_of_cell_log"
    __table_args__ = (
        CheckConstraint("minutes >= 0 AND minutes <= 1440", name="ck_ooc_minutes"),
        CheckConstraint("source IN ('facility', 'ingest')", name="ck_ooc_source"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    resident_id: Mapped[int] = mapped_column(ForeignKey("residents.id"), index=True)
    day: Mapped[date] = mapped_column(Date)
    minutes: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(8))
    entered_by: Mapped[int | None] = mapped_column(ForeignKey("staff.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class WelfareAck(Base):
    __tablename__ = "welfare_acks"
    id: Mapped[int] = mapped_column(primary_key=True)
    resident_id: Mapped[int] = mapped_column(ForeignKey("residents.id"), index=True)
    flag_type: Mapped[str] = mapped_column(String(32))
    staff_id: Mapped[int] = mapped_column(ForeignKey("staff.id"))
    note: Mapped[str] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    action: Mapped[str] = mapped_column(
        String(32), default="checked_in", server_default="checked_in"
    )


class Message(Base):
    """Text messages. Attorney messages are never stored: no body, not monitored (invariant 6)."""

    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint("direction IN ('out', 'in')", name="ck_msg_direction"),
        CheckConstraint("NOT (privileged AND monitored)", name="ck_msg_privileged_not_monitored"),
        CheckConstraint("NOT (privileged AND body IS NOT NULL)", name="ck_msg_privileged_no_body"),
        CheckConstraint(
            "delivery IN ('queued', 'sent', 'delivered', 'failed')", name="ck_msg_delivery"
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    resident_id: Mapped[int] = mapped_column(ForeignKey("residents.id"), index=True)
    contact_id: Mapped[int] = mapped_column(ForeignKey("contacts.id"))
    direction: Mapped[str] = mapped_column(String(3))
    body: Mapped[str | None] = mapped_column(EncryptedText("messages.body"), nullable=True)
    privileged: Mapped[bool] = mapped_column(Boolean)
    monitored: Mapped[bool] = mapped_column(Boolean)
    delivery: Mapped[str] = mapped_column(
        String(10), default="delivered", server_default="delivered"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class MessageFlag(Base):
    """A keyword match on a monitored message: a review item, never a sanction (invariant 12)."""

    __tablename__ = "message_flags"
    __table_args__ = (
        UniqueConstraint("message_id", "rule_id", name="uq_flag_message_rule"),
        CheckConstraint("status IN ('open', 'reviewed', 'referred')", name="ck_flag_status"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("messages.id"), index=True)
    rule_id: Mapped[str] = mapped_column(String(64))
    label: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(10), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("staff.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class VideoBooking(Base):
    """A scheduled video call. Minutes are reserved against the weekly allowance."""

    __tablename__ = "video_bookings"
    __table_args__ = (
        CheckConstraint(
            "status IN ('scheduled', 'started', 'cancelled', 'missed')", name="ck_booking_status"
        ),
        CheckConstraint("minutes > 0", name="ck_booking_minutes"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    resident_id: Mapped[int] = mapped_column(ForeignKey("residents.id"), index=True)
    contact_id: Mapped[int] = mapped_column(ForeignKey("contacts.id"))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    minutes: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(10), default="scheduled")
    call_id: Mapped[int | None] = mapped_column(ForeignKey("call_records.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class FacilityEvent(Base):
    """Events from the facility's own systems (for example cell cameras). Idempotent by event_id."""

    __tablename__ = "facility_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[str] = mapped_column(String(64), unique=True)
    type: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    result: Mapped[str] = mapped_column(String(64))


class ChessGame(Base):
    """A chess game or match. There is deliberately no chat, message, stake or item column here.

    Engine games are played on the device and only logged (level and result). Human matches have
    two residents, a random handle for each, the position, and how the match ended.
    """

    __tablename__ = "chess_games"
    __table_args__ = (
        CheckConstraint("opponent_kind IN ('engine', 'human')", name="ck_chess_opponent"),
        CheckConstraint("status IN ('waiting', 'active', 'finished')", name="ck_chess_status"),
        CheckConstraint("result IN ('white', 'black', 'draw')", name="ck_chess_result"),
        CheckConstraint("draw_offer_by IN ('white', 'black')", name="ck_chess_draw_offer"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    resident_id: Mapped[int] = mapped_column(ForeignKey("residents.id"), index=True)  # white
    black_resident_id: Mapped[int | None] = mapped_column(
        ForeignKey("residents.id"), nullable=True, index=True
    )
    opponent_kind: Mapped[str] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(10), default="active")
    provider_ref: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    level: Mapped[int | None] = mapped_column(Integer, nullable=True)  # engine games
    white_handle: Mapped[str | None] = mapped_column(String(32), nullable=True)
    black_handle: Mapped[str | None] = mapped_column(String(32), nullable=True)
    fen: Mapped[str | None] = mapped_column(String(100), nullable=True)
    result: Mapped[str | None] = mapped_column(String(8), nullable=True)
    result_reason: Mapped[str | None] = mapped_column(String(16), nullable=True)
    draw_offer_by: Mapped[str | None] = mapped_column(String(5), nullable=True)
    wait_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ChessMove(Base):
    """One move. Append-only: a played move is never changed."""

    __tablename__ = "chess_moves"
    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("chess_games.id"), index=True)
    ply: Mapped[int] = mapped_column(Integer)
    move: Mapped[str] = mapped_column(String(16))
    by: Mapped[str] = mapped_column(String(8))  # white | black (older rows: resident | opponent)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ApprovedContentSource(Base):
    """Allow-list for outside content. Everything not listed here is blocked (CSP follows it)."""

    __tablename__ = "approved_content_sources"
    __table_args__ = (CheckConstraint("kind IN ('bundled', 'external')", name="ck_source_kind"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    kind: Mapped[str] = mapped_column(String(10))
    base_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Holds protected-baseline content (legal, religious): cannot be switched off (invariant 1).
    protected: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("staff.id"), nullable=True)
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ReadingLog(Base):
    __tablename__ = "reading_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    resident_id: Mapped[int] = mapped_column(ForeignKey("residents.id"), index=True)
    item_id: Mapped[str] = mapped_column(String(64))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ReadingProgress(Base):
    """Furthest page reached per resident and text. Only ever moves forward."""

    __tablename__ = "reading_progress"
    __table_args__ = (UniqueConstraint("resident_id", "item_id", name="uq_reading_progress"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    resident_id: Mapped[int] = mapped_column(ForeignKey("residents.id"), index=True)
    item_id: Mapped[str] = mapped_column(String(64))
    page: Mapped[int] = mapped_column(Integer, default=0)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ReadingBookmark(Base):
    __tablename__ = "reading_bookmarks"
    __table_args__ = (
        UniqueConstraint("resident_id", "item_id", "page", name="uq_reading_bookmark"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    resident_id: Mapped[int] = mapped_column(ForeignKey("residents.id"), index=True)
    item_id: Mapped[str] = mapped_column(String(64))
    page: Mapped[int] = mapped_column(Integer)


JOB_TASK_TYPES = ("transcription_public_domain", "captioning", "labeling_non_personal")


class JobPartner(Base):
    """An outside organisation that supplies work (a mock in v1)."""

    __tablename__ = "job_partners"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(128))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class JobListing(Base):
    """Voluntary work. Task types are limited to ones that never handle anyone's personal data."""

    __tablename__ = "job_listings"
    __table_args__ = (CheckConstraint(f"task_type IN {JOB_TASK_TYPES}", name="ck_job_task_type"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    title: Mapped[str] = mapped_column(String(128))
    task_type: Mapped[str] = mapped_column(String(40))
    description: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    partner_id: Mapped[int | None] = mapped_column(ForeignKey("job_partners.id"), nullable=True)
    pay_per_task_cents: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class JobTask(Base):
    """One unit of work from a partner. Content is public or synthetic only (screened on entry)."""

    __tablename__ = "job_tasks"
    __table_args__ = (
        UniqueConstraint("listing_id", "external_id", name="uq_task_external"),
        CheckConstraint(f"kind IN {JOB_TASK_TYPES}", name="ck_task_kind"),
        CheckConstraint(
            "status IN ('open', 'claimed', 'accepted', 'rejected')", name="ck_task_status"
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("job_listings.id"), index=True)
    external_id: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(40))
    spec: Mapped[dict] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(10), default="open")
    claimed_by: Mapped[int | None] = mapped_column(ForeignKey("residents.id"), nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class TaskSubmission(Base):
    """What a resident handed in and whether the partner accepted it. Never edited."""

    __tablename__ = "task_submissions"
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("job_tasks.id"), unique=True)
    resident_id: Mapped[int] = mapped_column(ForeignKey("residents.id"), index=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("job_listings.id"))
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)  # kept only if accepted
    accepted: Mapped[bool] = mapped_column(Boolean)
    review_reason: Mapped[str] = mapped_column(String(32))
    pay_cents: Mapped[int] = mapped_column(Integer)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EarningsLedger(Base):
    """Append-only work earnings. 'earned' rows split the pay; 'payout' rows move the resident's
    share into the trust account. A nightly reconciliation checks these against the trust ledger
    (invariant 15)."""

    __tablename__ = "earnings_ledger"
    __table_args__ = (
        CheckConstraint("entry_type IN ('earned', 'payout')", name="ck_earn_type"),
        CheckConstraint(
            "entry_type <> 'earned' OR (gross_cents > 0 AND resident_cents >= 0"
            " AND facility_cents >= 0 AND deductions_cents >= 0"
            " AND gross_cents = resident_cents + facility_cents + deductions_cents"
            " AND submission_id IS NOT NULL AND trust_ledger_id IS NULL)",
            name="ck_earn_earned_adds_up",
        ),
        CheckConstraint(
            "entry_type <> 'payout' OR (resident_cents < 0 AND gross_cents = 0"
            " AND facility_cents = 0 AND deductions_cents = 0"
            " AND trust_ledger_id IS NOT NULL AND submission_id IS NULL)",
            name="ck_earn_payout_shape",
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    resident_id: Mapped[int] = mapped_column(ForeignKey("residents.id"), index=True)
    entry_type: Mapped[str] = mapped_column(String(8))
    submission_id: Mapped[int | None] = mapped_column(
        ForeignKey("task_submissions.id"), unique=True, nullable=True
    )
    gross_cents: Mapped[int] = mapped_column(Integer)
    resident_cents: Mapped[int] = mapped_column(Integer)  # signed: payouts are negative
    facility_cents: Mapped[int] = mapped_column(Integer)
    deductions_cents: Mapped[int] = mapped_column(Integer)
    split: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    trust_ledger_id: Mapped[int | None] = mapped_column(
        ForeignKey("trust_ledger.id"), unique=True, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class WorkLog(Base):
    """A resident's own record of joining, leaving and finishing tasks. Append-only. Staff see
    only totals, so work never becomes part of a behaviour record."""

    __tablename__ = "work_log"
    __table_args__ = (
        CheckConstraint(
            "event IN ('joined', 'left', 'task_accepted', 'task_rejected')", name="ck_worklog_event"
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    resident_id: Mapped[int] = mapped_column(ForeignKey("residents.id"), index=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("job_listings.id"))
    event: Mapped[str] = mapped_column(String(16))
    task_id: Mapped[int | None] = mapped_column(ForeignKey("job_tasks.id"), nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ReconciliationRun(Base):
    """The result of each nightly check that balances match their ledgers. Append-only."""

    __tablename__ = "reconciliation_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ok: Mapped[bool] = mapped_column(Boolean)
    checked: Mapped[dict] = mapped_column(JSONB)
    problems: Mapped[list] = mapped_column(JSONB)


class JobEnrollment(Base):
    """Opt-in record. Joining or leaving creates no points, sanction, or entitlement change."""

    __tablename__ = "job_enrollments"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'left')", name="ck_enroll_status"),
        Index(
            "uq_one_active_enrollment",
            "resident_id",
            "listing_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    resident_id: Mapped[int] = mapped_column(ForeignKey("residents.id"), index=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("job_listings.id"))
    status: Mapped[str] = mapped_column(String(8), default="active")
    opted_in_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RecBooking(Base):
    __tablename__ = "rec_bookings"
    __table_args__ = (
        UniqueConstraint("resident_id", "day", "slot", name="uq_rec_booking"),
        CheckConstraint("kind IN ('indoor', 'outdoor', 'program', 'visit')", name="ck_rec_kind"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    resident_id: Mapped[int] = mapped_column(ForeignKey("residents.id"), index=True)
    day: Mapped[date] = mapped_column(Date)
    slot: Mapped[str] = mapped_column(String(5))
    kind: Mapped[str] = mapped_column(String(8))
    block_id: Mapped[int | None] = mapped_column(
        ForeignKey("schedule_blocks.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


BLOCK_KINDS = ("indoor", "outdoor", "program", "visit")


class ScheduleBlock(Base):
    """One scheduled block for a unit on a day: indoor or outdoor recreation, a program, a visit.
    Who may sign up comes from `required_feature` through get_entitlements (never from the tier)."""

    __tablename__ = "schedule_blocks"
    __table_args__ = (
        UniqueConstraint("unit", "day", "kind", "start", name="uq_schedule_block"),
        CheckConstraint(f"kind IN {BLOCK_KINDS}", name="ck_block_kind"),
        CheckConstraint("status IN ('scheduled', 'cancelled')", name="ck_block_status"),
        CheckConstraint("minutes > 0 AND capacity > 0", name="ck_block_positive"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    unit: Mapped[str] = mapped_column(String(16), index=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    kind: Mapped[str] = mapped_column(String(8))
    start: Mapped[str] = mapped_column(String(5))  # HH:MM, facility local time as entered
    minutes: Mapped[int] = mapped_column(Integer)
    capacity: Mapped[int] = mapped_column(Integer)
    title: Mapped[str | None] = mapped_column(String(128), nullable=True)
    required_feature: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(10), default="scheduled")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("staff.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class OutOfCellEvent(Base):
    """An officer's tap-out or tap-in. Append-only; time out of the cell comes from these."""

    __tablename__ = "out_of_cell_events"
    __table_args__ = (
        CheckConstraint("event IN ('out', 'in')", name="ck_ooce_event"),
        CheckConstraint(
            "activity IN ('indoor', 'outdoor', 'program', 'visit', 'other')",
            name="ck_ooce_activity",
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    resident_id: Mapped[int] = mapped_column(ForeignKey("residents.id"), index=True)
    event: Mapped[str] = mapped_column(String(3))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    activity: Mapped[str] = mapped_column(String(8))
    block_id: Mapped[int | None] = mapped_column(ForeignKey("schedule_blocks.id"), nullable=True)
    entered_by: Mapped[int | None] = mapped_column(ForeignKey("staff.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class WelfareFlag(Base):
    """A welfare flag staff must acknowledge. Stored so it can be tracked and escalated."""

    __tablename__ = "welfare_flags"
    __table_args__ = (
        CheckConstraint("status IN ('open', 'acknowledged', 'cleared')", name="ck_wflag_status"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    resident_id: Mapped[int] = mapped_column(ForeignKey("residents.id"), index=True)
    flag_type: Mapped[str] = mapped_column(String(32))
    severity: Mapped[str] = mapped_column(String(10))
    detail: Mapped[dict] = mapped_column(
        JSONB, default=dict
    )  # includes the resident's own baseline
    status: Mapped[str] = mapped_column(String(12), default="open")
    raised_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_by: Mapped[int | None] = mapped_column(ForeignKey("staff.id"), nullable=True)
    action: Mapped[str | None] = mapped_column(String(32), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    cleared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class KeepSeparate(Base):
    """Two residents who must never be paired or scheduled together. Stored once, a < b."""

    __tablename__ = "keep_separate"
    __table_args__ = (
        CheckConstraint("resident_a_id < resident_b_id", name="ck_keep_separate_order"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    resident_a_id: Mapped[int] = mapped_column(ForeignKey("residents.id"), index=True)
    resident_b_id: Mapped[int] = mapped_column(ForeignKey("residents.id"), index=True)
    added_by: Mapped[int | None] = mapped_column(ForeignKey("staff.id"), nullable=True)
    added_at: Mapped[datetime] = _now()
    reason: Mapped[str] = mapped_column(String(200))  # staff only; never shown to residents
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_by: Mapped[int | None] = mapped_column(ForeignKey("staff.id"), nullable=True)


class ReentryEvent(Base):
    """Append-only checklist history; the latest event per item is its current state."""

    __tablename__ = "reentry_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    resident_id: Mapped[int] = mapped_column(ForeignKey("residents.id"), index=True)
    item_code: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(12))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    staff_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id"), nullable=True)
    at: Mapped[datetime] = _now()


class OutcomeRecord(Base):
    """Outcome data entered later from customer records. Append-only; a fix is a new row."""

    __tablename__ = "outcome_records"
    __table_args__ = (
        CheckConstraint("window_months IN (6, 12, 24)", name="ck_outcome_window"),
        CheckConstraint("outcome IN ('no_return', 'returned', 'unknown')", name="ck_outcome_value"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    resident_id: Mapped[int] = mapped_column(ForeignKey("residents.id"), index=True)
    window_months: Mapped[int] = mapped_column(Integer)
    outcome: Mapped[str] = mapped_column(String(10))
    source: Mapped[str] = mapped_column(String(80))
    corrects_id: Mapped[int | None] = mapped_column(ForeignKey("outcome_records.id"), nullable=True)
    entered_by: Mapped[int | None] = mapped_column(ForeignKey("staff.id"), nullable=True)
    entered_at: Mapped[datetime] = _now()
    batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("outcome_import_batches.id"), nullable=True, index=True
    )


class OutcomeImportBatch(Base):
    """One CSV import of outcomes. Append-only, like the rows it created."""

    __tablename__ = "outcome_import_batches"
    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String(80))
    source: Mapped[str] = mapped_column(String(80))
    rows_total: Mapped[int] = mapped_column(Integer)
    rows_new: Mapped[int] = mapped_column(Integer)
    rows_correcting: Mapped[int] = mapped_column(Integer)
    rows_unchanged: Mapped[int] = mapped_column(Integer)
    entered_by: Mapped[int | None] = mapped_column(ForeignKey("staff.id"), nullable=True)
    entered_at: Mapped[datetime] = _now()


class DevicePairing(Base):
    """A short-lived, single-use code that lets a new kiosk fetch its own token. Only a hash."""

    __tablename__ = "device_pairings"
    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), index=True)
    code_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("staff.id"), nullable=True)
    created_at: Mapped[datetime] = _now()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DeviceCommand(Base):
    """Staff actions on a device: pause (lock) until a time, lift it, or restart the kiosk app."""

    __tablename__ = "device_commands"
    __table_args__ = (
        CheckConstraint("kind IN ('lock', 'unlock', 'restart')", name="ck_device_command_kind"),
        CheckConstraint("kind <> 'lock' OR ends_at IS NOT NULL", name="ck_lock_has_end"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), index=True)
    kind: Mapped[str] = mapped_column(String(8))
    reason: Mapped[str] = mapped_column(String(200))
    issued_by: Mapped[int | None] = mapped_column(ForeignKey("staff.id"), nullable=True)
    issued_at: Mapped[datetime] = _now()
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SweepState(Base):
    """When a periodic check last ran, so a busy screen does not re-run it on every refresh."""

    __tablename__ = "sweep_state"
    name: Mapped[str] = mapped_column(String(32), primary_key=True)
    last_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


@event.listens_for(Contact, "before_insert")
@event.listens_for(Contact, "before_update")
def _contact_blind_index(mapper, connection, target: Contact) -> None:
    """Keeps the searchable keyed hash of the number in step with the (encrypted) number."""
    target.phone_hash = blind_index(target.phone_ref) if target.phone_ref else None
