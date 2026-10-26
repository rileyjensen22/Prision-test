"""Staff account administration (admins only): create, deactivate, reset a password or MFA.

Every step is audited with the administrator's stated reason. A temporary password is shown once
to the administrator and must be changed at the person's first sign-in. Nobody can use these steps
on their own account (they have the change-password screen), and the last active administrator
cannot be deactivated.
"""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from isd import passwords
from isd.auth import hash_password
from isd.models import ROLES, Staff
from isd.services.audit import Actor, append_audit


class AccountError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _reason(reason: str) -> str:
    if len(reason.strip()) < 3:
        raise AccountError("REASON_REQUIRED", "a reason is required")
    return reason.strip()[:300]


def _other(session: Session, actor: Actor, staff_id: int) -> Staff:
    if staff_id == actor.id:
        raise AccountError("OWN_ACCOUNT", "use the change-password screen for your own account")
    target = session.get(Staff, staff_id)
    if target is None:
        raise AccountError("NOT_FOUND", "account not found")
    return target


def list_accounts(session: Session) -> list[dict]:
    return [
        {
            "id": s.id,
            "username": s.username,
            "role": s.role,
            "active": s.active,
            "mfa_enabled": s.mfa_enabled,
            "must_change_password": s.must_change_password,
        }
        for s in session.execute(select(Staff).order_by(Staff.username)).scalars()
    ]


def create_account(
    session: Session, actor: Actor, username: str, role: str, reason: str, now: datetime
) -> tuple[Staff, str]:
    why = _reason(reason)
    name = username.strip().lower()
    if (
        not name.replace("_", "").replace("-", "").replace(".", "").isalnum()
        or not 3 <= len(name) <= 64
    ):
        raise AccountError("BAD_USERNAME", "3 to 64 letters, digits, dot, dash or underscore")
    if role not in ROLES:
        raise AccountError("BAD_ROLE", "unknown role")
    if session.execute(select(Staff.id).where(Staff.username == name)).first():
        raise AccountError("USERNAME_TAKEN", "that username is already used")
    temp = passwords.temporary()
    staff = Staff(
        username=name, role=role, password_hash=hash_password(temp), must_change_password=True
    )
    session.add(staff)
    session.flush()
    append_audit(
        session,
        actor,
        "staff_account_created",
        "staff",
        staff.id,
        "ACCOUNT_CREATED",
        payload={"username": name, "role": role, "reason": why},
    )
    return staff, temp


def set_active(
    session: Session, actor: Actor, staff_id: int, active: bool, reason: str, now: datetime
) -> Staff:
    why = _reason(reason)
    target = _other(session, actor, staff_id)
    if target.active == active:
        return target
    if not active and target.role == "admin":
        admins = session.execute(
            select(func.count()).where(Staff.role == "admin", Staff.active.is_(True))
        ).scalar()
        if admins <= 1:
            raise AccountError("LAST_ADMIN", "there must be at least one active administrator")
    target.active = active
    append_audit(
        session,
        actor,
        "staff_account_activated" if active else "staff_account_deactivated",
        "staff",
        target.id,
        "ACCOUNT_ACTIVE" if active else "ACCOUNT_DEACTIVATED",
        payload={"username": target.username, "reason": why},
    )
    session.flush()
    return target


def reset_password(
    session: Session, actor: Actor, staff_id: int, reason: str, now: datetime
) -> str:
    why = _reason(reason)
    target = _other(session, actor, staff_id)
    temp = passwords.temporary()
    target.password_hash = hash_password(temp)
    target.password_changed_at = now  # signs out every session the person had
    target.must_change_password = True
    append_audit(
        session,
        actor,
        "staff_password_reset",
        "staff",
        target.id,
        "PASSWORD_RESET",
        payload={"username": target.username, "reason": why},  # never the password
    )
    session.flush()
    return temp


def reset_mfa(session: Session, actor: Actor, staff_id: int, reason: str, now: datetime) -> Staff:
    why = _reason(reason)
    target = _other(session, actor, staff_id)
    target.mfa_secret = None
    target.mfa_enabled = False
    target.mfa_recovery_hashes = None
    target.mfa_last_step = None
    target.password_changed_at = now  # ends their current sessions
    append_audit(
        session,
        actor,
        "staff_mfa_reset",
        "staff",
        target.id,
        "MFA_RESET",
        payload={"username": target.username, "reason": why},
    )
    session.flush()
    return target
