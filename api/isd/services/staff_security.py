"""Staff sign-in security: authenticator app (TOTP) enrolment and checks, recovery codes, password
change. Every step is audited; secrets and codes never appear in the audit log."""

import hashlib
import secrets
import time
from datetime import datetime

from sqlalchemy.orm import Session

from isd import passwords, totp
from isd.auth import hash_password, verify_password
from isd.models import Staff
from isd.services.audit import Actor, append_audit

RECOVERY_CODES = 10


class SecurityError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.replace("-", "").upper().encode()).hexdigest()


def new_recovery_codes() -> list[str]:
    return [
        "-".join(
            [
                secrets.token_hex(2).upper(),
                secrets.token_hex(2).upper(),
                secrets.token_hex(2).upper(),
            ]
        )
        for _ in range(RECOVERY_CODES)
    ]


def start_mfa_setup(session: Session, staff: Staff) -> dict:
    if staff.mfa_enabled:
        raise SecurityError("ALREADY_ENABLED", "an authenticator app is already set up")
    staff.mfa_secret = totp.new_secret()
    staff.mfa_enabled = False
    append_audit(
        session, Actor(staff.id, staff.role), "mfa_setup_started", "staff", staff.id, "MFA_SETUP"
    )
    session.flush()
    return {
        "secret": staff.mfa_secret,
        "otpauth_uri": totp.provisioning_uri(staff.mfa_secret, staff.username),
    }


def enable_mfa(session: Session, staff: Staff, code: str, now: datetime) -> list[str]:
    if staff.mfa_enabled or not staff.mfa_secret:
        raise SecurityError("NOT_STARTED", "start the setup first")
    step = totp.verify(staff.mfa_secret, code, now.timestamp())
    if step is None:
        raise SecurityError("BAD_CODE", "that code did not match; check the time on your phone")
    codes = new_recovery_codes()
    staff.mfa_enabled = True
    staff.mfa_last_step = step
    staff.mfa_recovery_hashes = [_hash_code(c) for c in codes]
    append_audit(
        session, Actor(staff.id, staff.role), "mfa_enabled", "staff", staff.id, "MFA_ENABLED"
    )
    session.flush()
    return codes


def check_second_factor(
    session: Session, staff: Staff, code: str | None, recovery: str | None, now: datetime
) -> bool:
    """True if a valid authenticator code (not used before) or an unused recovery code was given."""
    if code:
        step = totp.verify(staff.mfa_secret or "", code, now.timestamp(), staff.mfa_last_step)
        if step is not None:
            staff.mfa_last_step = step
            return True
    if recovery:
        h = _hash_code(recovery)
        left = list(staff.mfa_recovery_hashes or [])
        if h in left:
            left.remove(h)
            staff.mfa_recovery_hashes = left
            append_audit(
                session,
                Actor(staff.id, staff.role),
                "mfa_recovery_code_used",
                "staff",
                staff.id,
                "MFA_RECOVERY",
                payload={"codes_left": len(left)},
            )
            return True
    return False


def change_password(session: Session, staff: Staff, current: str, new: str, now: datetime) -> None:
    if not verify_password(staff.password_hash, current):
        raise SecurityError("WRONG_PASSWORD", "your current password is not right")
    try:
        passwords.check(new, staff.username, current)
    except passwords.WeakPassword as e:
        raise SecurityError("WEAK_PASSWORD", str(e)) from e
    staff.password_hash = hash_password(new)
    staff.password_changed_at = now
    staff.must_change_password = False
    append_audit(
        session,
        Actor(staff.id, staff.role),
        "password_changed",
        "staff",
        staff.id,
        "PASSWORD_CHANGED",
    )
    session.flush()


def now_ts() -> float:
    return time.time()
