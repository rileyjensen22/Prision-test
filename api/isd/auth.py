"""Staff auth (argon2 passwords, HMAC-signed bearer tokens) and server-side RBAC."""

import base64
import hashlib
import hmac
import json
import time

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from isd import limits, settings
from isd.db import get_db
from isd.models import Staff

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def _sign(body: str) -> str:
    return hmac.new(settings.SECRET_KEY.encode(), body.encode(), hashlib.sha256).hexdigest()


def make_token(staff_id: int, ttl: int | None = None) -> str:
    claims = {"sub": staff_id, "exp": int(time.time()) + (ttl or settings.TOKEN_TTL_SECONDS)}
    body = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode()
    return f"{body}.{_sign(body)}"


def parse_token(token: str) -> int | None:
    body, _, sig = token.partition(".")
    if not body or not hmac.compare_digest(sig, _sign(body)):
        return None
    try:
        claims = json.loads(base64.urlsafe_b64decode(body))
    except ValueError:
        return None
    return claims["sub"] if claims.get("exp", 0) > time.time() else None


_DUMMY_HASH = _hasher.hash("not-a-real-password")


def authenticate(session: Session, username: str, password: str) -> Staff | None:
    staff = session.execute(select(Staff).where(Staff.username == username)).scalar()
    # Always do one password check, so an unknown username takes as long as a wrong password.
    ok = verify_password(staff.password_hash if staff else _DUMMY_HASH, password)
    return staff if staff and staff.active and ok else None


def current_staff(
    request: Request,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> Staff:
    scheme, _, token = (authorization or "").partition(" ")
    staff_id = parse_token(token) if scheme.lower() == "bearer" else None
    staff = db.get(Staff, staff_id) if staff_id else None
    if not staff or not staff.active:
        raise HTTPException(401, "not authenticated")
    limits.enforce("staff", f"staff:{staff.id}")
    return staff


def require_roles(*roles: str):
    """Route dependency: only the listed roles pass. Role is read from the DB, not the token."""

    def dependency(staff: Staff = Depends(current_staff)) -> Staff:
        if staff.role not in roles:
            raise HTTPException(403, "role not permitted")
        return staff

    dependency.allowed_roles = roles  # type: ignore[attr-defined]
    return dependency


# ---- Kiosk device identity (CLAUDE.md 7: identity = device -> cell -> resident, no login) ----
def hash_device_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class DeviceContext:
    def __init__(self, device, resident_id: int):
        self.device, self.resident_id = device, resident_id


def current_device(
    request: Request,
    x_device_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> DeviceContext:
    from isd.models import Device, DeviceAssignment

    device = (
        db.execute(
            select(Device).where(Device.token_hash == hash_device_token(x_device_token or ""))
        ).scalar()
        if x_device_token
        else None
    )
    if device is None:
        raise HTTPException(401, "unknown device")
    limits.enforce("device", f"device:{device.id}")
    assignment = db.execute(
        select(DeviceAssignment)
        .where(DeviceAssignment.device_id == device.id, DeviceAssignment.ended_at.is_(None))
        .order_by(DeviceAssignment.assigned_at.desc())
        .limit(1)
    ).scalar()
    if assignment is None:
        raise HTTPException(409, "device is not assigned to a resident")
    return DeviceContext(device, assignment.resident_id)


current_device.device_auth = True  # marker checked by the route-guard test


def current_paired_device(
    request: Request,
    x_device_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """A kiosk that has its token but may not be assigned to a resident yet (heartbeats)."""
    from isd.models import Device

    device = (
        db.execute(
            select(Device).where(Device.token_hash == hash_device_token(x_device_token or ""))
        ).scalar()
        if x_device_token
        else None
    )
    if device is None:
        raise HTTPException(401, "unknown device")
    limits.enforce("device", f"device:{device.id}")
    return device


current_paired_device.device_auth = True  # type: ignore[attr-defined]
