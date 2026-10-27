"""Versioned config (invariant 9). Every change is a new row plus an audit entry."""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from isd.config_loader import validate_section
from isd.models import ConfigVersion
from isd.services.audit import Actor, append_audit

# The sections every resident view needs. A request session (see isd.db.get_db) loads them all in
# one query the first time any is asked for and keeps them for the rest of that request. Other
# sessions (scripts, tests) always read the database, so they never see stale config.
HOT_SECTIONS = ("tiers", "points", "sanctions", "offenses", "compliance", "chess")


def get_current(session: Session, name: str) -> ConfigVersion | None:
    cache = session.info.get("config_cache")
    if cache is not None and name in HOT_SECTIONS:
        if not cache:
            cache.update(_fetch_many(session, HOT_SECTIONS))
            cache["_loaded"] = True  # marks the cache as filled even if a section is missing
        return cache.get(name)
    return session.execute(
        select(ConfigVersion)
        .where(ConfigVersion.name == name)
        .order_by(ConfigVersion.version.desc())
        .limit(1)
    ).scalar()


def get_current_many(session: Session, names: tuple[str, ...]) -> dict[str, ConfigVersion]:
    """The current version of several sections in one query."""
    if session.info.get("config_cache") is not None and set(names) <= set(HOT_SECTIONS):
        found = {n: get_current(session, n) for n in names}
        return {n: row for n, row in found.items() if row is not None}
    return _fetch_many(session, names)


def _fetch_many(session: Session, names: tuple[str, ...]) -> dict[str, ConfigVersion]:
    rows = session.execute(
        select(ConfigVersion)
        .where(ConfigVersion.name.in_(names))
        .distinct(ConfigVersion.name)
        .order_by(ConfigVersion.name, ConfigVersion.version.desc())
    ).scalars()
    return {r.name: r for r in rows}


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
    if "config_cache" in session.info:
        session.info["config_cache"] = {}  # the next read in this request sees the new version
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
