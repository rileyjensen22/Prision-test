"""Sandbox overrides for "view as resident" (CLAUDE.md 9.1). Pure: changes the *inputs* to the
entitlement engine, never its rules, so the simulated view is produced by the same code path
as the real one."""

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta

from isd.engine.config import EngineConfig
from isd.engine.entitlements import OffenseFact, ResidentFacts, SanctionFact
from isd.engine.features import SCOPES

MAX_PRIOR_RETURNS = 60


@dataclass(frozen=True)
class SandboxSanction:
    code: str
    hours_remaining: float | None = None  # None = the full duration from now


@dataclass(frozen=True)
class SandboxOverrides:
    tier: int | None = None  # replaces the earned tier
    prior_returns: int | None = None  # replaces the repeat-return count (changes the ceiling)
    offense_categories: tuple[str, ...] | None = None  # replaces the resident's offense flags
    add_sanctions: tuple[SandboxSanction, ...] = ()
    clear_sanctions: bool = False  # ignore the resident's real sanctions
    language: str | None = None
    text_size: str | None = None
    reading_level: str | None = None
    captions: bool | None = None
    notes: dict = field(default_factory=dict)


def validate(ov: SandboxOverrides, cfg: EngineConfig) -> None:
    if ov.tier is not None and not 1 <= ov.tier <= 10:
        raise ValueError("tier must be 1..10")
    if ov.prior_returns is not None and not 0 <= ov.prior_returns <= MAX_PRIOR_RETURNS:
        raise ValueError(f"prior_returns must be 0..{MAX_PRIOR_RETURNS}")
    for cat in ov.offense_categories or ():
        if cat not in cfg.offense_rules:
            raise ValueError(f"unknown offense category {cat!r}")
    for s in ov.add_sanctions:
        rule = cfg.infractions.get(s.code)
        if rule is None:
            raise ValueError(f"unknown infraction code {s.code!r}")
        if s.hours_remaining is not None and not 0 < s.hours_remaining <= rule.duration_hours:
            raise ValueError(f"{s.code}: hours_remaining must be within its {rule.duration_hours}h")


def apply_to_facts(
    facts: ResidentFacts, ov: SandboxOverrides, cfg: EngineConfig, at_time: datetime
) -> ResidentFacts:
    validate(ov, cfg)
    sanctions = () if ov.clear_sanctions else facts.sanctions
    for i, s in enumerate(ov.add_sanctions):
        rule = cfg.infractions[s.code]
        remaining = timedelta(hours=s.hours_remaining or rule.duration_hours)
        ends = at_time + remaining
        starts = ends - timedelta(hours=rule.duration_hours)
        assert rule.scope in SCOPES
        sanctions += (
            SanctionFact(-(i + 1), rule.code, rule.scope, starts, ends),
        )  # negative id: not real
    offenses = (
        facts.offenses
        if ov.offense_categories is None
        else tuple(OffenseFact(c) for c in ov.offense_categories)
    )
    return replace(
        facts,
        earned_tier=ov.tier if ov.tier is not None else facts.earned_tier,
        prior_returns=ov.prior_returns if ov.prior_returns is not None else facts.prior_returns,
        offenses=offenses,
        sanctions=sanctions,
    )


def apply_to_settings(settings: dict, ov: SandboxOverrides) -> dict:
    out = dict(settings)
    for key in ("language", "text_size", "reading_level", "captions"):
        value = getattr(ov, key)
        if value is not None:
            out[key] = value
    return out
