from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from isd import limits, settings
from isd.auth import authenticate, make_token, password_version, require_roles
from isd.db import get_db
from isd.models import ROLES, Staff
from isd.providers import get_sso
from isd.services import staff_security
from isd.services.audit import SYSTEM, Actor, append_audit

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)  # a cap, so huge inputs cannot burn CPU
    totp: str | None = Field(default=None, max_length=12)  # the 6-digit code from the app
    recovery: str | None = Field(default=None, max_length=32)  # one recovery code instead


@router.post("/login")
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)) -> dict:
    ip = limits.client_ip(request)
    name = body.username.strip().lower()[:64]
    key = f"{ip}|{name}"
    limits.enforce("login_attempts_ip", ip)
    failures = limits.LIMITERS["login_failures"]
    on = settings.RATE_LIMIT_ENABLED
    if on and failures.blocked(key):
        raise HTTPException(
            429,
            "too many failed sign-ins; try again later",
            headers={"Retry-After": str(failures.retry_after(key))},
        )
    staff = authenticate(db, body.username, body.password)
    if not staff:
        if on:
            failures.hit(key)
            if failures.count(key) == failures.limit:  # this failure just locked it
                append_audit(
                    db, SYSTEM, "login_locked", "staff", name, "LOGIN_LOCKED", payload={"ip": ip}
                )
                db.commit()  # keep the entry even though we answer with an error
        raise HTTPException(401, "invalid credentials")
    if staff.mfa_enabled:
        if not body.totp and not body.recovery:
            raise HTTPException(
                401,
                {"code": "MFA_REQUIRED", "message": "enter the code from your authenticator app"},
            )
        if not staff_security.check_second_factor(
            db, staff, body.totp, body.recovery, datetime.now(UTC)
        ):
            if on:
                failures.hit(key)
            db.commit()
            raise HTTPException(401, "invalid credentials")
    failures.reset(key)
    append_audit(
        db,
        Actor(staff.id, staff.role),
        "login",
        "staff",
        staff.id,
        "LOGIN",
        payload={"method": "password", "mfa": staff.mfa_enabled},
    )
    needs_enrolment = settings.STAFF_MFA_REQUIRED and not staff.mfa_enabled
    pv = password_version(staff)
    token = make_token(staff.id, scope="enroll" if needs_enrolment else None, pv=pv)
    return {
        "token": token,
        "role": staff.role,
        "mfa_enrollment_required": needs_enrolment,
        "must_change_password": staff.must_change_password,
    }


class SSOIn(BaseModel):
    assertion: str = Field(min_length=1, max_length=2048)


@router.post("/sso")
def sso_login(body: SSOIn, request: Request, db: Session = Depends(get_db)) -> dict:
    """Sign in through the identity-provider interface. The mock provider is development only."""
    if not settings.SSO_MOCK_ENABLED:
        raise HTTPException(404, "not found")
    limits.enforce("login_attempts_ip", limits.client_ip(request))
    username = get_sso().subject_for(body.assertion)
    staff = (
        db.execute(select(Staff).where(Staff.username == username)).scalar() if username else None
    )
    if staff is None or not staff.active:
        raise HTTPException(401, "invalid credentials")
    append_audit(
        db,
        Actor(staff.id, staff.role),
        "login",
        "staff",
        staff.id,
        "LOGIN",
        payload={"method": "sso"},
    )
    return {"token": make_token(staff.id), "role": staff.role}


@router.post("/refresh")
def refresh(staff: Staff = Depends(require_roles(*ROLES))) -> dict:
    """A fresh token for a valid one. Staff who stop using the app are signed out at expiry."""
    return {"token": make_token(staff.id, pv=password_version(staff)), "role": staff.role}


@router.get("/me")
def me(staff: Staff = Depends(require_roles(*ROLES))) -> dict:
    return {
        "id": staff.id,
        "username": staff.username,
        "role": staff.role,
        "mfa_enabled": staff.mfa_enabled,
        "must_change_password": staff.must_change_password,
    }


def _fail(e: staff_security.SecurityError) -> HTTPException:
    return HTTPException(422, {"code": e.code, "message": str(e)})


class ChangePasswordIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


@router.post("/change-password")
def change_password(
    body: ChangePasswordIn,
    staff: Staff = Depends(require_roles(*ROLES)),
    db: Session = Depends(get_db),
) -> dict:
    try:
        staff_security.change_password(
            db, staff, body.current_password, body.new_password, datetime.now(UTC)
        )
    except staff_security.SecurityError as e:
        raise _fail(e) from e
    # Every earlier token stops working; this one is the new session.
    return {"token": make_token(staff.id, pv=password_version(staff)), "role": staff.role}


@router.post("/mfa/setup")
def mfa_setup(staff: Staff = Depends(require_roles(*ROLES)), db: Session = Depends(get_db)) -> dict:
    try:
        return staff_security.start_mfa_setup(db, staff)
    except staff_security.SecurityError as e:
        raise _fail(e) from e


class MfaEnableIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=6, max_length=12)


@router.post("/mfa/enable")
def mfa_enable(
    body: MfaEnableIn,
    staff: Staff = Depends(require_roles(*ROLES)),
    db: Session = Depends(get_db),
) -> dict:
    try:
        codes = staff_security.enable_mfa(db, staff, body.code, datetime.now(UTC))
    except staff_security.SecurityError as e:
        raise _fail(e) from e
    # The recovery codes are shown once. The token stops being restricted to enrolment.
    return {"recovery_codes": codes, "token": make_token(staff.id, pv=password_version(staff))}
