"""Staff auth (argon2 passwords, HMAC-signed bearer tokens) and server-side RBAC."""

import base64
import hashlib
import hmac
import json
import time

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from isd import settings
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


def authenticate(session: Session, username: str, password: str) -> Staff | None:
    staff = session.execute(select(Staff).where(Staff.username == username)).scalar()
    if staff and staff.active and verify_password(staff.password_hash, password):
        return staff
    return None


def current_staff(
    authorization: str | None = Header(default=None), db: Session = Depends(get_db)
) -> Staff:
    scheme, _, token = (authorization or "").partition(" ")
    staff_id = parse_token(token) if scheme.lower() == "bearer" else None
    staff = db.get(Staff, staff_id) if staff_id else None
    if not staff or not staff.active:
        raise HTTPException(401, "not authenticated")
    return staff


def require_roles(*roles: str):
    """Route dependency: only the listed roles pass. Role is read from the DB, not the token."""

    def dependency(staff: Staff = Depends(current_staff)) -> Staff:
        if staff.role not in roles:
            raise HTTPException(403, "role not permitted")
        return staff

    dependency.allowed_roles = roles  # type: ignore[attr-defined]
    return dependency
