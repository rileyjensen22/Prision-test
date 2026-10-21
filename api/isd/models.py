"""Phase 1 data model. Business rules live in isd.engine, not here."""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

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
    created_at: Mapped[datetime] = _now()


class Cell(Base):
    __tablename__ = "cells"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)


class Device(Base):
    __tablename__ = "devices"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    token_hash: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)


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
    __table_args__ = (CheckConstraint(f"type IN {CONTACT_TYPES}", name="ck_contact_type"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    resident_id: Mapped[int] = mapped_column(ForeignKey("residents.id"))
    name: Mapped[str] = mapped_column(String(128))
    type: Mapped[str] = mapped_column(String(16))
    approved: Mapped[bool] = mapped_column(Boolean, default=True)
    blocked: Mapped[bool] = mapped_column(Boolean, default=False)  # no-contact order


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
