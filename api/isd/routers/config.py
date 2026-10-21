from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from isd.auth import require_roles
from isd.db import get_db
from isd.models import ROLES, Staff
from isd.services import config_store
from isd.services.audit import Actor

router = APIRouter(prefix="/config", tags=["config"])


@router.get("")
def list_sections(
    _: Staff = Depends(require_roles(*ROLES)), db: Session = Depends(get_db)
) -> list[dict]:
    from isd.config_loader import CONFIG_FILES

    out = []
    for name in CONFIG_FILES:
        row = config_store.get_current(db, name)
        out.append({"name": name, "version": row.version if row else None})
    return out


@router.get("/{name}")
def get_config(
    name: str, _: Staff = Depends(require_roles(*ROLES)), db: Session = Depends(get_db)
) -> dict:
    row = config_store.get_current(db, name)
    if not row:
        raise HTTPException(404, "unknown config section")
    return {"name": name, "version": row.version, "payload": row.payload}


@router.get("/{name}/versions")
def versions(
    name: str,
    _: Staff = Depends(require_roles("admin", "auditor")),
    db: Session = Depends(get_db),
) -> list[dict]:
    return [
        {
            "version": v.version,
            "reason": v.reason,
            "created_by": v.created_by,
            "created_at": v.created_at.isoformat(),
        }
        for v in config_store.list_versions(db, name)
    ]


class ConfigIn(BaseModel):
    payload: dict[str, Any]
    reason: str


@router.put("/{name}")
def put_config(
    name: str,
    body: ConfigIn,
    staff: Staff = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
) -> dict:
    try:
        row = config_store.set_config(
            db, Actor(staff.id, staff.role), name, body.payload, body.reason
        )
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return {"name": name, "version": row.version}
