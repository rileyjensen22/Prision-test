"""Enrolling kiosks, their health reports and staff commands (pause, lift, restart).

A pause is read by `get_entitlements` as a `DeviceLockFact`; this module only records it.
Nothing here sees a camera picture: the heartbeat says whether a camera exists, not what it sees.
"""

import hashlib
import secrets
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from isd.auth import hash_device_token
from isd.models import Cell, Device, DeviceAssignment, DeviceCommand, DevicePairing, Resident
from isd.services.audit import SYSTEM, Actor, append_audit
from isd.services.config_store import get_current
from isd.services.device_locks import locks_from_commands

_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no 0/O/1/I/L
HEALTH_KEYS = {
    "storage_used_mb",
    "storage_quota_mb",
    "camera",
    "microphone",
    "app_version",
    "queue_pending",
    "online",
}
PRESENCE = ("ok", "missing", "blocked", "unknown")


class FleetError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _compliance(session: Session) -> dict:
    return get_current(session, "compliance").payload


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.strip().upper().encode()).hexdigest()


def _device(session: Session, code: str) -> Device:
    device = session.execute(select(Device).where(Device.code == code)).scalar()
    if device is None:
        raise FleetError("NOT_FOUND", "device not found")
    return device


def create_device(session: Session, actor: Actor, code: str, now: datetime) -> Device:
    code = code.strip()
    if not 3 <= len(code) <= 32 or not code.replace("-", "").replace("_", "").isalnum():
        raise FleetError("BAD_CODE", "device code is 3 to 32 letters, digits, - or _")
    if session.execute(select(Device.id).where(Device.code == code)).first():
        raise FleetError("CODE_TAKEN", "that device code already exists")
    device = Device(code=code)
    session.add(device)
    session.flush()
    append_audit(session, actor, "device_created", "device", code, reason_code="DEVICE_ENROLL")
    return device


def issue_pairing(session: Session, actor: Actor, device_code: str, now: datetime) -> dict:
    """A one-time code for the kiosk to enter. Older unused codes for the device stop working."""
    device = _device(session, device_code)
    for old in session.execute(
        select(DevicePairing).where(
            DevicePairing.device_id == device.id, DevicePairing.used_at.is_(None)
        )
    ).scalars():
        old.used_at = now  # retired, not deleted
    code = "".join(secrets.choice(_ALPHABET) for _ in range(8))
    minutes = int(_compliance(session)["pairing_code_minutes"])
    session.add(
        DevicePairing(
            device_id=device.id,
            code_hash=_hash_code(code),
            created_by=actor.id,
            created_at=now,
            expires_at=now + timedelta(minutes=minutes),
        )
    )
    append_audit(
        session,
        actor,
        "device_pairing_issued",
        "device",
        device.code,
        reason_code="DEVICE_ENROLL",
        payload={"valid_minutes": minutes},  # never the code
    )
    session.flush()
    return {"device": device.code, "code": code, "expires_at": now + timedelta(minutes=minutes)}


def pair(session: Session, code: str, now: datetime) -> dict:
    """Exchanges a valid pairing code for a new device token (the old token, if any, dies)."""
    row = session.execute(
        select(DevicePairing).where(DevicePairing.code_hash == _hash_code(code))
    ).scalar()
    if row is None or row.used_at is not None or row.expires_at <= now:
        raise FleetError("BAD_PAIRING_CODE", "that code is not valid")
    device = session.get(Device, row.device_id)
    token = secrets.token_urlsafe(32)
    device.token_hash = hash_device_token(token)
    row.used_at = now
    append_audit(
        session, SYSTEM, "device_paired", "device", device.code, reason_code="DEVICE_ENROLL"
    )
    return {"token": token, "device": device.code}


def record_heartbeat(
    session: Session, device: Device, body: dict, acks: list[int], now: datetime
) -> list[dict]:
    """Stores the latest health report and returns the commands the device should act on."""
    device.health = {k: v for k, v in body.items() if k in HEALTH_KEYS}
    device.health_at = now
    pending = session.execute(
        select(DeviceCommand)
        .where(
            DeviceCommand.device_id == device.id,
            DeviceCommand.kind == "restart",
            DeviceCommand.acked_at.is_(None),
        )
        .order_by(DeviceCommand.id)
    ).scalars()
    out = []
    for cmd in pending:
        if cmd.id in acks:
            cmd.acked_at = now
        else:
            out.append({"id": cmd.id, "kind": cmd.kind})
    return out


def _command(
    session: Session,
    actor: Actor,
    device_code: str,
    kind: str,
    reason: str,
    now: datetime,
    ends_at: datetime | None = None,
) -> DeviceCommand:
    if len(reason.strip()) < 3:
        raise FleetError("REASON_REQUIRED", "a reason is required")
    device = _device(session, device_code)
    cmd = DeviceCommand(
        device_id=device.id,
        kind=kind,
        reason=reason.strip()[:200],
        issued_by=actor.id,
        issued_at=now,
        ends_at=ends_at,
    )
    session.add(cmd)
    session.flush()
    append_audit(
        session,
        actor,
        f"device_{kind}",
        "device",
        device.code,
        reason_code=f"DEVICE_{kind.upper()}",
        payload={"reason": cmd.reason, "ends_at": ends_at.isoformat() if ends_at else None},
    )
    return cmd


def lock(
    session: Session, actor: Actor, device_code: str, hours: float, reason: str, now: datetime
) -> DeviceCommand:
    limit = float(_compliance(session)["device_lock_max_hours"])
    if not 0 < hours <= limit:
        raise FleetError("BAD_DURATION", f"a pause lasts up to {limit:g} hours")
    return _command(
        session, actor, device_code, "lock", reason, now, ends_at=now + timedelta(hours=hours)
    )


def unlock(
    session: Session, actor: Actor, device_code: str, reason: str, now: datetime
) -> DeviceCommand:
    return _command(session, actor, device_code, "unlock", reason, now)


def restart(
    session: Session, actor: Actor, device_code: str, reason: str, now: datetime
) -> DeviceCommand:
    return _command(session, actor, device_code, "restart", reason, now)


def fleet(session: Session, now: datetime) -> list[dict]:
    offline_after = timedelta(minutes=int(_compliance(session)["offline_alert_minutes"]))
    rows = session.execute(
        select(Device, DeviceAssignment, Cell, Resident)
        .outerjoin(
            DeviceAssignment,
            (DeviceAssignment.device_id == Device.id) & DeviceAssignment.ended_at.is_(None),
        )
        .outerjoin(Cell, Cell.id == DeviceAssignment.cell_id)
        .outerjoin(Resident, Resident.id == DeviceAssignment.resident_id)
        .order_by(Device.code)
    ).all()
    commands: dict[int, list[DeviceCommand]] = {}
    for c in session.execute(
        select(DeviceCommand).where(DeviceCommand.kind.in_(("lock", "unlock")))
    ).scalars():
        commands.setdefault(c.device_id, []).append(c)
    by_device = {d: locks_from_commands(cmds) for d, cmds in commands.items()}
    out = []
    for device, assignment, cell, resident in rows:
        seen = max(filter(None, [device.last_sync_at, device.health_at]), default=None)
        locks = [(i, s, e) for i, s, e in by_device.get(device.id, []) if s <= now < e]
        out.append(
            {
                "device": device.code,
                "paired": device.token_hash is not None,
                "cell": cell.code if cell else None,
                "resident": resident.code if resident else None,
                "last_seen": seen.isoformat() if seen else None,
                "offline": bool(assignment) and (seen is None or now - seen > offline_after),
                "health": device.health,
                "health_at": device.health_at.isoformat() if device.health_at else None,
                "locked_until": max(e for _, _, e in locks).isoformat() if locks else None,
            }
        )
    return out
