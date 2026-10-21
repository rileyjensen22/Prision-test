from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from isd.auth import authenticate, make_token, require_roles
from isd.db import get_db
from isd.models import ROLES, Staff

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)) -> dict:
    staff = authenticate(db, body.username, body.password)
    if not staff:
        raise HTTPException(401, "invalid credentials")
    return {"token": make_token(staff.id), "role": staff.role}


@router.get("/me")
def me(staff: Staff = Depends(require_roles(*ROLES))) -> dict:
    return {"id": staff.id, "username": staff.username, "role": staff.role}
