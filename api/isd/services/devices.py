"""Device credentials. The server stores only a hash; the token is shown once, when it is issued."""

import secrets
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from isd.auth import hash_device_token
from isd.models import Device
from isd.services.audit import Actor, append_audit


def rotate_token(session: Session, actor: Actor, device_code: str, now: datetime) -> str:
    """Issues a new random token for the device. The old one stops working immediately."""
    device = session.execute(select(Device).where(Device.code == device_code)).scalar()
    if device is None:
        raise LookupError("device not found")
    token = secrets.token_urlsafe(32)
    device.token_hash = hash_device_token(token)
    append_audit(
        session,
        actor,
        "device_token_rotated",
        "device",
        device.code,
        "DEVICE_TOKEN",
        payload={"device": device.code},  # never the token, nor any part of it
    )
    return token
