"""Pure entitlement composition (invariant 2). DB loading lives in services.entitlement_service.

Order (CLAUDE.md 4.1): baseline -> tier grants capped at ceiling -> offense restrictions
-> active sanctions -> contact blocks. Steps 3-5 only ever touch non-baseline features.
"""

from dataclasses import dataclass, field
from datetime import datetime

from isd.engine.ceiling import ceiling_tier
from isd.engine.config import EngineConfig
from isd.engine.features import (
    APPEAL,
    ASK_STAFF,
    BASELINE_FEATURES,
    NON_BASELINE_FEATURES,
    SCOPES,
)


@dataclass(frozen=True)
class Reason:
    code: str
    source: str  # tier | ceiling | offense | sanction
    how_to_appeal: str
    ends_at: datetime | None = None
    detail: str = ""
    ref_id: int | None = None
    params: dict[str, int | str] = field(default_factory=dict)  # for client-side translation


@dataclass(frozen=True)
class FeatureEntitlement:
    allowed: bool
    limits: dict[str, int] = field(default_factory=dict)
    reasons: tuple[Reason, ...] = ()


@dataclass(frozen=True)
class SanctionFact:
    id: int
    reason_code: str
    scope: str
    starts_at: datetime
    ends_at: datetime


@dataclass(frozen=True)
class OffenseFact:
    category: str
    next_review_at: datetime | None = None


@dataclass(frozen=True)
class ResidentFacts:
    earned_tier: int
    prior_returns: int
    offenses: tuple[OffenseFact, ...] = ()
    sanctions: tuple[SanctionFact, ...] = ()
    blocked_contact_ids: tuple[int, ...] = ()


@dataclass(frozen=True)
class Entitlements:
    at_time: datetime
    earned_tier: int
    ceiling_tier: int
    effective_tier: int
    features: dict[str, FeatureEntitlement]
    blocked_contact_ids: tuple[int, ...]
    next_change_at: datetime | None  # earliest sanction start/end after at_time

    def allowed(self, feature: str) -> bool:
        return self.features[feature].allowed


def _tier_grant(feature: str, tier: int, cfg: EngineConfig) -> dict[str, int] | None:
    """Limits granted to `feature` at `tier`, or None if not granted."""
    row = cfg.tiers[tier]
    match feature:
        case "calls":
            return {"minutes_per_day": row.calls_min_day} if row.calls_min_day > 0 else None
        case "texting":
            return {"messages_per_day": row.texts_day} if row.texts_day > 0 else None
        case "video":
            return {"minutes_per_week": row.video_min_week} if row.video_min_week > 0 else None
        case "commissary":
            usd = row.commissary_usd_week
            return {"dollars_per_week": usd} if usd > 0 else None
        case "chess_engine":
            return {} if row.chess in ("engine", "human") else None
        case "chess_human":
            return {} if row.chess == "human" else None
        case "outdoor_rec":
            hours = row.outdoor_rec_h_day
            return {"minutes_per_day": hours * 60} if hours > 0 else None
        case "reading_general":
            return {} if tier >= cfg.general_reading_from_tier else None
        case "reading_expanded":
            return {} if tier >= cfg.expanded_catalog_from_tier else None
        case "advanced_education":
            return {} if tier >= cfg.advanced_education_from_tier else None
    raise ValueError(f"unknown feature {feature}")


def _first_tier_granting(feature: str, cfg: EngineConfig) -> int | None:
    return next((t for t in sorted(cfg.tiers) if _tier_grant(feature, t, cfg) is not None), None)


def _tier_step(feature: str, facts: ResidentFacts, eff: int, ceil: int, cfg: EngineConfig):
    granted = _tier_grant(feature, eff, cfg)
    if granted is not None:
        return granted, None
    if _tier_grant(feature, facts.earned_tier, cfg) is not None:
        why = Reason(
            "TIER_CEILING",
            "ceiling",
            ASK_STAFF,
            detail=f"Repeat-return ceiling is tier {ceil}",
            params={"ceiling": ceil},
        )
    else:
        needed = _first_tier_granting(feature, cfg)
        why = Reason(
            "TIER_LOCKED",
            "tier",
            ASK_STAFF,
            detail=f"Unlocks at tier {needed}",
            params={"tier": needed or 0},
        )
    return None, why


def compute_entitlements(
    facts: ResidentFacts, cfg: EngineConfig, at_time: datetime
) -> Entitlements:
    ceil = ceiling_tier(facts.prior_returns, cfg.ceiling_N, cfg.ceiling_p)
    eff = max(1, min(facts.earned_tier, ceil))

    limits: dict[str, dict[str, int] | None] = {}
    reasons: dict[str, list[Reason]] = {f: [] for f in NON_BASELINE_FEATURES}
    for feature in NON_BASELINE_FEATURES:  # step 2: tier grants capped at ceiling
        limits[feature], why = _tier_step(feature, facts, eff, ceil, cfg)
        if why:
            reasons[feature].append(why)

    for offense in facts.offenses:  # step 3: offense restrictions
        rule = cfg.offense_rules.get(offense.category)
        if rule is None:
            continue
        for feature in rule.blocked_features & NON_BASELINE_FEATURES:
            reasons[feature].append(
                Reason(
                    "OFFENSE_RESTRICTION",
                    "offense",
                    APPEAL,
                    ends_at=offense.next_review_at,
                    detail=rule.reason_text,
                )
            )

    for s in facts.sanctions:  # step 4: active sanctions
        if not s.starts_at <= at_time < s.ends_at:
            continue
        for feature in SCOPES[s.scope] & NON_BASELINE_FEATURES:
            reasons[feature].append(
                Reason(s.reason_code, "sanction", APPEAL, ends_at=s.ends_at, ref_id=s.id)
            )

    features: dict[str, FeatureEntitlement] = {}
    for feature in NON_BASELINE_FEATURES:
        ok = limits[feature] is not None and not reasons[feature]
        features[feature] = FeatureEntitlement(
            allowed=ok,
            limits=dict(limits[feature] or {}) if ok else {},
            reasons=tuple(reasons[feature]),
        )
    # Step 5 (contact blocks) is per-contact, so it is returned rather than folded into a feature.
    for feature in BASELINE_FEATURES:  # step 1, applied last so nothing above can touch it
        lim = {"minutes_per_day": cfg.baseline_out_of_cell_minutes}
        features[feature] = FeatureEntitlement(
            True, lim if feature == "out_of_cell_minimum" else {}
        )

    boundaries = [t for s in facts.sanctions for t in (s.starts_at, s.ends_at) if t > at_time]
    return Entitlements(
        at_time=at_time,
        earned_tier=facts.earned_tier,
        ceiling_tier=ceil,
        effective_tier=eff,
        features=features,
        blocked_contact_ids=tuple(sorted(facts.blocked_contact_ids)),
        next_change_at=min(boundaries, default=None),
    )
