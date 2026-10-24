"""get_entitlements: the single entry point for feature access (invariant 2). Read-only."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from isd.engine.config import EngineConfig
from isd.engine.entitlements import (
    DeviceLockFact,
    Entitlements,
    OffenseFact,
    ResidentFacts,
    SanctionFact,
    compute_entitlements,
)
from isd.engine.sandbox import SandboxOverrides, apply_to_facts
from isd.models import Contact, OffenseFlag, Resident, Sanction, TierHistory
from isd.services.config_store import get_current
from isd.services.device_locks import locks_for_residents

ENGINE_SECTIONS = ("tiers", "points", "sanctions", "offenses")


def load_engine_config(session: Session) -> EngineConfig:
    sections = {}
    for name in ENGINE_SECTIONS:
        row = get_current(session, name)
        if row is None:
            raise LookupError(f"config section {name!r} has not been seeded")
        sections[name] = row.payload
    return EngineConfig.from_sections(sections)


def earned_tier(session: Session, resident_id: int, at_time: datetime) -> int:
    return earned_tiers(session, [resident_id], at_time)[resident_id]


def earned_tiers(session: Session, resident_ids: list[int], at_time: datetime) -> dict[int, int]:
    rows = session.execute(
        select(TierHistory.resident_id, TierHistory.to_tier)
        .where(TierHistory.resident_id.in_(resident_ids), TierHistory.at <= at_time)
        .distinct(TierHistory.resident_id)
        .order_by(TierHistory.resident_id, TierHistory.at.desc(), TierHistory.id.desc())
    ).all()
    found = {rid: tier for rid, tier in rows}
    return {rid: found.get(rid) or 1 for rid in resident_ids}


def load_facts_many(
    session: Session, resident_ids: list[int], at_time: datetime
) -> dict[int, ResidentFacts]:
    """Facts for many residents in a fixed number of queries. `load_facts` uses this too, so the
    roster and the single-resident path can never disagree."""
    ids = list(dict.fromkeys(resident_ids))
    if not ids:
        return {}
    returns = {
        rid: n
        for rid, n in session.execute(
            select(Resident.id, Resident.prior_returns).where(Resident.id.in_(ids))
        )
    }
    missing = [i for i in ids if i not in returns]
    if missing:
        raise LookupError(f"resident {missing[0]} not found")
    tiers = earned_tiers(session, ids, at_time)
    sanctions: dict[int, list[SanctionFact]] = {}
    for s in session.execute(
        select(Sanction).where(Sanction.resident_id.in_(ids), Sanction.status == "active")
    ).scalars():
        if s.starts_at and s.ends_at:
            sanctions.setdefault(s.resident_id, []).append(
                SanctionFact(s.id, s.reason_code, s.scope, s.starts_at, s.ends_at)
            )
    offenses: dict[int, list[OffenseFact]] = {}
    for o in session.execute(
        select(OffenseFlag).where(OffenseFlag.resident_id.in_(ids), OffenseFlag.added_at <= at_time)
    ).scalars():
        offenses.setdefault(o.resident_id, []).append(
            OffenseFact(o.offense_category, o.next_review_at)
        )
    blocked: dict[int, list[int]] = {}
    for cid, rid in session.execute(
        select(Contact.id, Contact.resident_id).where(
            Contact.resident_id.in_(ids), Contact.blocked.is_(True)
        )
    ):
        blocked.setdefault(rid, []).append(cid)
    locks = locks_for_residents(session, ids)
    return {
        rid: ResidentFacts(
            earned_tier=tiers[rid],
            prior_returns=returns[rid],
            offenses=tuple(offenses.get(rid, ())),
            sanctions=tuple(sanctions.get(rid, ())),
            blocked_contact_ids=tuple(blocked.get(rid, ())),
            device_locks=tuple(DeviceLockFact(i, a, b) for i, a, b in locks.get(rid, ())),
        )
        for rid in ids
    }


def load_facts(session: Session, resident_id: int, at_time: datetime) -> ResidentFacts:
    return load_facts_many(session, [resident_id], at_time)[resident_id]


def get_entitlements_many(
    session: Session, resident_ids: list[int], at_time: datetime, cfg: EngineConfig | None = None
) -> dict[int, Entitlements]:
    """The same answers as `get_entitlements`, for a list of residents (the staff roster)."""
    cfg = cfg or load_engine_config(session)
    return {
        rid: compute_entitlements(f, cfg, at_time)
        for rid, f in load_facts_many(session, resident_ids, at_time).items()
    }


def get_entitlements(
    session: Session,
    resident_id: int,
    at_time: datetime,
    cfg: EngineConfig | None = None,
    overrides: SandboxOverrides | None = None,
) -> Entitlements:
    """Everything the resident can use at `at_time`, with a reason for every lock.

    Performs no writes, so sandbox / time-travel views are safe (CLAUDE.md 9.1).
    `overrides` (sandbox only) change the inputs, never the rules.
    """
    cfg = cfg or load_engine_config(session)
    facts = load_facts(session, resident_id, at_time)
    if overrides is not None:
        facts = apply_to_facts(facts, overrides, cfg, at_time)
    return compute_entitlements(facts, cfg, at_time)
