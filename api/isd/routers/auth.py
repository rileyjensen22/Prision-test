from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from isd import limits, settings
from isd.auth import authenticate, make_token, require_roles
from isd.db import get_db
from isd.models import ROLES, Staff
from isd.providers import get_sso
from isd.services.audit import SYSTEM, Actor, append_audit

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)  # a cap, so huge inputs cannot burn CPU


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
    failures.reset(key)
    append_audit(
        db,
        Actor(staff.id, staff.role),
        "login",
        "staff",
        staff.id,
        "LOGIN",
        payload={"method": "password"},
    )
    return {"token": make_token(staff.id), "role": staff.role}


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
    return {"token": make_token(staff.id), "role": staff.role}


@router.get("/me")
def me(staff: Staff = Depends(require_roles(*ROLES))) -> dict:
    return {"id": staff.id, "username": staff.username, "role": staff.role}
