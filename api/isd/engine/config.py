"""Typed, immutable view of the versioned config sections used by the engine."""

from dataclasses import dataclass
from typing import Any

from isd.engine.features import NON_BASELINE_FEATURES, SCOPES


@dataclass(frozen=True)
class TierRow:
    calls_min_day: int
    texts_day: int
    video_min_week: int
    commissary_usd_week: int
    chess: str  # none | engine | human
    outdoor_rec_h_day: int


@dataclass(frozen=True)
class InfractionRule:
    code: str
    label: str
    scope: str
    duration_hours: int
    confirmation: (
        str  # officer_immediate | supervisor_always | supervisor_evidence | system_event_supervisor
    )
    severity: str  # minor | major


@dataclass(frozen=True)
class OffenseRule:
    offense_category: str
    blocked_features: frozenset[str]
    reason_text: str
    required_reviewer_role: str
    review_interval_days: int


@dataclass(frozen=True)
class EngineConfig:
    thresholds: tuple[int, ...]
    hysteresis: float
    max_drops_per_7_days: int
    baseline_out_of_cell_minutes: int
    ceiling_N: float
    ceiling_p: float
    tiers: dict[int, TierRow]
    general_reading_from_tier: int
    expanded_catalog_from_tier: int
    advanced_education_from_tier: int
    infractions: dict[str, InfractionRule]
    offense_rules: dict[str, OffenseRule]
    point_events: dict[str, dict[str, Any]]
    officer_weekly_cap: int
    appeal_review_hours: int

    @classmethod
    def from_sections(cls, sections: dict[str, dict]) -> "EngineConfig":
        t, sanc = sections["tiers"], sections["sanctions"]
        content = t["content"]
        return cls(
            thresholds=tuple(t["promotion_thresholds"]),
            hysteresis=float(t["demotion_hysteresis"]),
            max_drops_per_7_days=int(t["max_tier_drop_per_7_days"]),
            baseline_out_of_cell_minutes=int(t["baseline_out_of_cell_minutes"]),
            ceiling_N=float(t["repeat_return"]["N"]),
            ceiling_p=float(t["repeat_return"]["p"]),
            tiers={int(k): TierRow(**v) for k, v in t["tiers"].items()},
            general_reading_from_tier=content["general_reading_from_tier"],
            expanded_catalog_from_tier=content["expanded_catalog_from_tier"],
            advanced_education_from_tier=content["advanced_education_from_tier"],
            infractions={c: InfractionRule(code=c, **v) for c, v in sanc["infractions"].items()},
            offense_rules={
                r["offense_category"]: OffenseRule(
                    offense_category=r["offense_category"],
                    blocked_features=frozenset(r["blocked_features"]),
                    reason_text=r["reason_text"],
                    required_reviewer_role=r["required_reviewer_role"],
                    review_interval_days=r["review_interval_days"],
                )
                for r in sections["offenses"]["offense_restrictions"]
            },
            point_events=sections["points"]["events"],
            officer_weekly_cap=int(sanc["officer_weekly_immediate_sanction_cap"]),
            appeal_review_hours=int(sanc["appeal_review_hours"]),
        )


def validate_sanctions(payload: dict) -> None:
    for code, rule in payload["infractions"].items():
        if rule["scope"] not in SCOPES:
            raise ValueError(f"{code}: unknown scope {rule['scope']!r}")
        if rule["severity"] not in ("minor", "major"):
            raise ValueError(f"{code}: severity must be minor or major")
        if rule["confirmation"] not in (
            "officer_immediate",
            "supervisor_always",
            "supervisor_evidence",
            "system_event_supervisor",
        ):
            raise ValueError(f"{code}: unknown confirmation rule")


def validate_offenses(payload: dict) -> None:
    for row in payload["offense_restrictions"]:
        unknown = set(row["blocked_features"]) - NON_BASELINE_FEATURES
        if unknown:  # baseline features can never be blocked (invariant 1)
            raise ValueError(f"{row['offense_category']}: cannot block {sorted(unknown)}")
