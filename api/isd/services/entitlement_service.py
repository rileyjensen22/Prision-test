"""get_entitlements: the single entry point for feature access (invariant 2). Read-only."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from isd.engine.config import EngineConfig
from isd.engine.entitlements import (
    Entitlements,
    OffenseFact,
    ResidentFacts,
    SanctionFact,
    compute_entitlements,
)
from isd.engine.sandbox import SandboxOverrides, apply_to_facts
from isd.models import Contact, OffenseFlag, Resident, Sanction, TierHistory
from isd.services.config_store import get_current

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
    row = session.execute(
        select(TierHistory.to_tier)
        .where(TierHistory.resident_id == resident_id, TierHistory.at <= at_time)
        .order_by(TierHistory.at.desc(), TierHistory.id.desc())
        .limit(1)
    ).scalar()
    return row or 1


def load_facts(session: Session, resident_id: int, at_time: datetime) -> ResidentFacts:
    resident = session.get(Resident, resident_id)
    if resident is None:
        raise LookupError(f"resident {resident_id} not found")
    sanctions = session.execute(
        select(Sanction).where(Sanction.resident_id == resident_id, Sanction.status == "active")
    ).scalars()
    offenses = session.execute(
        select(OffenseFlag).where(
            OffenseFlag.resident_id == resident_id, OffenseFlag.added_at <= at_time
        )
    ).scalars()
    blocked = session.execute(
        select(Contact.id).where(Contact.resident_id == resident_id, Contact.blocked.is_(True))
    ).scalars()
    return ResidentFacts(
        earned_tier=earned_tier(session, resident_id, at_time),
        prior_returns=resident.prior_returns,
        offenses=tuple(OffenseFact(o.offense_category, o.next_review_at) for o in offenses),
        sanctions=tuple(
            SanctionFact(s.id, s.reason_code, s.scope, s.starts_at, s.ends_at)
            for s in sanctions
            if s.starts_at and s.ends_at
        ),
        blocked_contact_ids=tuple(blocked),
    )


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
