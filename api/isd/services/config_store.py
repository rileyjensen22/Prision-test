"""Versioned config (invariant 9). Every change is a new row plus an audit entry."""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from isd.config_loader import validate_section
from isd.models import ConfigVersion
from isd.services.audit import Actor, append_audit


def get_current(session: Session, name: str) -> ConfigVersion | None:
    return session.execute(
        select(ConfigVersion)
        .where(ConfigVersion.name == name)
        .order_by(ConfigVersion.version.desc())
        .limit(1)
    ).scalar()


def list_versions(session: Session, name: str) -> list[ConfigVersion]:
    return list(
        session.execute(
            select(ConfigVersion).where(ConfigVersion.name == name).order_by(ConfigVersion.version)
        ).scalars()
    )


def set_config(
    session: Session, actor: Actor, name: str, payload: dict[str, Any], reason: str
) -> ConfigVersion:
    if not reason.strip():
        raise ValueError("a reason is required for config changes")
    validate_section(name, payload)
    latest = session.execute(
        select(func.max(ConfigVersion.version)).where(ConfigVersion.name == name)
    ).scalar()
    row = ConfigVersion(
        name=name,
        version=(latest or 0) + 1,
        payload=payload,
        reason=reason,
        created_by=actor.id,
    )
    session.add(row)
    session.flush()
    append_audit(
        session,
        actor,
        "config_change",
        "config",
        name,
        reason_code="CONFIG_EDIT",
        payload={"version": row.version, "reason": reason},
    )
    return row
