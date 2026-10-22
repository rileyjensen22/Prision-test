"""Admitting a resident: one step that creates the record and everything around it, all audited.

Nothing here decides what the resident may do; offense categories only record which config rows
apply, and `get_entitlements` still reads them from there.
"""

import re
import secrets
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from isd.engine.contacts import ContactInvalid, clean_request
from isd.models import (
    Cell,
    Contact,
    Device,
    DeviceAssignment,
    KeepSeparate,
    OffenseFlag,
    Resident,
)
from isd.services.audit import Actor, append_audit
from isd.services.config_store import get_current

_CODE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{2,31}$")


class IntakeError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass
class IntakeContact:
    name: str
    type: str
    phone: str


@dataclass
class IntakeRequest:
    display_name: str
    cell_code: str
    device_code: str
    reason: str
    code: str | None = None
    language: str = "en"
    text_size: str = "normal"
    reading_level: str = "standard"
    captions: bool = False
    prior_returns: int = 0
    prior_returns_source: str | None = None
    release_date: date | None = None
    offense_categories: list[str] = field(default_factory=list)
    contacts: list[IntakeContact] = field(default_factory=list)
    keep_separate: list[tuple[str, str]] = field(default_factory=list)  # (resident code, reason)


def _validate_basics(req: IntakeRequest, now: datetime) -> None:
    if len(req.display_name.strip()) < 2:
        raise IntakeError("BAD_NAME", "enter the resident's name")
    if req.code is not None and not _CODE.match(req.code):
        raise IntakeError("BAD_CODE", "code is 3 to 32 letters, digits, - or _")
    if req.prior_returns < 0 or req.prior_returns > 50:
        raise IntakeError("BAD_PRIOR_RETURNS", "prior returns must be between 0 and 50")
    if req.prior_returns and not (req.prior_returns_source or "").strip():
        raise IntakeError("SOURCE_REQUIRED", "say where the prior-returns number came from")
    if req.release_date is not None and req.release_date < now.date():
        raise IntakeError("BAD_RELEASE_DATE", "the release date is in the past")
    if len(req.reason.strip()) < 3:
        raise IntakeError("REASON_REQUIRED", "a reason is required")


def _check_categories(session: Session, categories: list[str]) -> dict[str, dict]:
    rules = {
        r["offense_category"]: r
        for r in get_current(session, "offenses").payload["offense_restrictions"]
    }
    for cat in categories:
        if cat not in rules:
            raise IntakeError("UNKNOWN_OFFENSE_CATEGORY", f"{cat} is not a configured category")
    if len(set(categories)) != len(categories):
        raise IntakeError("DUPLICATE_OFFENSE_CATEGORY", "a category was listed twice")
    return rules


def _check_contacts(session: Session, contacts: list[IntakeContact]) -> list[tuple[str, str, str]]:
    limit = int(get_current(session, "compliance").payload["contact_max_approved"])
    if len(contacts) > limit:
        raise IntakeError("CONTACT_LIST_FULL", f"at most {limit} contacts")
    try:
        cleaned = [clean_request(c.name, c.type, c.phone) for c in contacts]
    except ContactInvalid as e:
        raise IntakeError(e.code, str(e)) from e
    if len({c[2] for c in cleaned}) != len(cleaned):
        raise IntakeError("DUPLICATE", "the same number was listed twice")
    return cleaned


def _find_place(session: Session, cell_code: str, device_code: str) -> tuple[Cell, Device]:
    cell = session.execute(select(Cell).where(Cell.code == cell_code)).scalar()
    device = session.execute(select(Device).where(Device.code == device_code)).scalar()
    if cell is None or device is None:
        raise IntakeError("NOT_FOUND", "cell or device not found")
    open_rows = session.execute(
        select(DeviceAssignment).where(
            DeviceAssignment.ended_at.is_(None),
            (DeviceAssignment.cell_id == cell.id) | (DeviceAssignment.device_id == device.id),
        )
    ).scalars()
    if next(iter(open_rows), None) is not None:
        raise IntakeError("OCCUPIED", "that cell or device is already assigned")
    return cell, device


def _find_separate(session: Session, entries: list[tuple[str, str]]) -> list[tuple[Resident, str]]:
    found = []
    for code, reason in entries:
        other = session.execute(select(Resident).where(Resident.code == code)).scalar()
        if other is None:
            raise IntakeError("NOT_FOUND", f"no resident with code {code}")
        if len(reason.strip()) < 3:
            raise IntakeError("REASON_REQUIRED", "give a reason for each keep-separate entry")
        found.append((other, reason.strip()[:200]))
    return found


def intake(session: Session, actor: Actor, req: IntakeRequest, now: datetime) -> Resident:
    _validate_basics(req, now)
    rules = _check_categories(session, req.offense_categories)
    contacts = _check_contacts(session, req.contacts)
    cell, device = _find_place(session, req.cell_code, req.device_code)
    separate = _find_separate(session, req.keep_separate)
    code = req.code or f"RES-{secrets.token_hex(3).upper()}"
    if session.execute(select(Resident.id).where(Resident.code == code)).first():
        raise IntakeError("CODE_TAKEN", "that resident code is already used")

    resident = Resident(
        code=code,
        display_name=req.display_name.strip(),
        language=req.language,
        text_size=req.text_size,
        reading_level=req.reading_level,
        captions=req.captions,
        prior_returns=req.prior_returns,
        prior_returns_source=(req.prior_returns_source or "").strip() or None,
        release_date=req.release_date,
        created_at=now,
    )
    session.add(resident)
    session.flush()
    _record(session, actor, resident, req, rules, contacts, separate, cell, device, now)
    return resident


def _record(session, actor, resident, req, rules, contacts, separate, cell, device, now) -> None:
    target = resident.code
    reason = req.reason.strip()
    append_audit(
        session,
        actor,
        "resident_intake",
        "resident",
        target,
        reason_code="INTAKE",
        payload={
            "reason": reason,
            "settings": {
                "language": req.language,
                "text_size": req.text_size,
                "reading_level": req.reading_level,
                "captions": req.captions,
            },
        },
    )
    if req.prior_returns:
        append_audit(
            session,
            actor,
            "prior_returns_set",
            "resident",
            target,
            reason_code="PRIOR_RETURNS",
            payload={"prior_returns": req.prior_returns, "source": resident.prior_returns_source},
        )
    if req.release_date:
        append_audit(
            session,
            actor,
            "release_date_set",
            "resident",
            target,
            reason_code="RELEASE_DATE",
            payload={"release_date": req.release_date.isoformat(), "reason": reason},
        )
    for cat in req.offense_categories:
        interval = int(rules[cat]["review_interval_days"])
        session.add(
            OffenseFlag(
                resident_id=resident.id,
                offense_category=cat,
                added_by=actor.id,
                added_at=now,
                next_review_at=now + timedelta(days=interval),
            )
        )
        append_audit(
            session,
            actor,
            "offense_category_added",
            "resident",
            target,
            reason_code="OFFENSE_CATEGORY",
            payload={"category": cat, "review_in_days": interval},
        )
    for name, kind, phone in contacts:
        session.add(
            Contact(
                resident_id=resident.id,
                name=name,
                type=kind,
                phone_ref=phone,
                approved=True,
                status="approved",
                requested_by="staff",
                reviewed_by=actor.id,
                reviewed_at=now,
            )
        )
        append_audit(
            session,
            actor,
            "contact_added",
            "resident",
            target,
            reason_code="CONTACT_ADDED",
            payload={"type": kind},  # no name or number in the log
        )
    for other, why in separate:
        a, b = sorted((resident.id, other.id))
        session.add(
            KeepSeparate(
                resident_a_id=a, resident_b_id=b, added_by=actor.id, added_at=now, reason=why
            )
        )
        append_audit(
            session,
            actor,
            "keep_separate_added",
            "resident",
            target,
            reason_code="KEEP_SEPARATE",
            payload={"with": other.code},
        )
    session.add(
        DeviceAssignment(
            device_id=device.id,
            cell_id=cell.id,
            resident_id=resident.id,
            assigned_by=actor.id,
            assigned_at=now,
        )
    )
    append_audit(
        session,
        actor,
        "device_assignment",
        "device",
        device.code,
        reason_code="ASSIGNMENT_CHANGE",
        payload={"from_resident": None, "to_resident": resident.id, "reason": reason},
    )
    session.flush()


def options(session: Session) -> dict:
    """What the intake form can choose from: vacant cells and devices, categories, contact types."""
    taken = list(
        session.execute(
            select(DeviceAssignment.cell_id, DeviceAssignment.device_id).where(
                DeviceAssignment.ended_at.is_(None)
            )
        )
    )
    used_cells = {c for c, _ in taken}
    used_devices = {d for _, d in taken}
    cells = session.execute(select(Cell).order_by(Cell.code)).scalars()
    devices = session.execute(select(Device).order_by(Device.code)).scalars()
    cats = get_current(session, "offenses").payload["offense_restrictions"]
    return {
        "vacant_cells": [{"code": c.code, "unit": c.unit} for c in cells if c.id not in used_cells],
        "free_devices": [d.code for d in devices if d.id not in used_devices],
        "offense_categories": [
            {"code": r["offense_category"], "reason_text": r["reason_text"]} for r in cats
        ],
        "contact_types": ["family", "friend", "attorney"],
    }


def keep_separate_codes(session: Session, resident_id: int) -> list[str]:
    """Codes of the residents currently kept apart from this one (staff view only)."""
    rows = session.execute(
        select(KeepSeparate).where(
            KeepSeparate.ended_at.is_(None),
            (KeepSeparate.resident_a_id == resident_id)
            | (KeepSeparate.resident_b_id == resident_id),
        )
    ).scalars()
    other_ids = [
        r.resident_b_id if r.resident_a_id == resident_id else r.resident_a_id for r in rows
    ]
    if not other_ids:
        return []
    return sorted(
        session.execute(select(Resident.code).where(Resident.id.in_(other_ids))).scalars()
    )
