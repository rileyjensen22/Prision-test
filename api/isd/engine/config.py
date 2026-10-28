"""Typed, immutable view of the versioned config sections used by the engine."""

from dataclasses import dataclass
from typing import Any

from isd.engine.features import ALL_FEATURES, NON_BASELINE_FEATURES, SCOPES
from isd.engine.reading import CATALOG_FEATURE


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
    o = payload.get("outlier")
    if o is not None and not (
        o["window_days"] > 0
        and o["z_threshold"] > 0
        and o["min_peers"] >= 2
        and o["min_count"] >= 1
    ):
        raise ValueError("outlier settings out of range")
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


def validate_commissary(payload: dict) -> None:
    seen = set()
    for item in payload["items"]:
        if item["code"] in seen:
            raise ValueError(f"duplicate commissary item {item['code']}")
        seen.add(item["code"])
        if item["price_cents"] <= 0 or not 1 <= item["min_tier"] <= 10:
            raise ValueError(f"{item['code']}: price must be positive and min_tier in 1..10")
    if payload["max_deposit_cents"] <= 0:
        raise ValueError("max_deposit_cents must be positive")


def validate_courses(payload: dict) -> None:
    """The courses section: shared settings plus each course in the shape course_format builds."""
    from isd.course_format import validate_course_set

    quiz = payload["quiz_defaults"]
    if any(not isinstance(quiz[k], int) or quiz[k] < 1 for k in quiz):
        raise ValueError("quiz_defaults must be positive whole numbers")
    if "basic" not in payload.get("uncapped_attempt_levels", []):
        raise ValueError("basic education has no attempt cap (invariant 1)")
    if not set(payload.get("uncapped_attempt_levels", [])) <= {"basic", "advanced", "program"}:
        raise ValueError("uncapped_attempt_levels must be course levels")
    for c in payload["courses"]:
        bank = c["quiz"]["bank"]
        if not c["lessons"] or not bank:
            raise ValueError(f"{c['code']}: needs lessons and quiz questions")
        if not 0 < c["pass_mark"] <= 1 or c["level"] not in ("basic", "advanced", "program"):
            raise ValueError(f"{c['code']}: bad level or pass_mark")
        draw = c["quiz"].get("draw", quiz["draw"])
        if draw > len(bank):
            raise ValueError(f"{c['code']}: draws {draw} questions from a bank of {len(bank)}")
        for q in bank:
            if not 0 <= q["answer"] < len(q["choices"]):
                raise ValueError(f"{c['code']}/{q['id']}: answer index out of range")
    validate_course_set(payload["courses"], payload)


def validate_welfare(payload: dict) -> None:
    if payload["recent_days"] < 1 or payload["baseline_days"] < payload["recent_days"]:
        raise ValueError("baseline_days must be at least recent_days, and both positive")
    if not 0 < payload["drop_ratio"] < 1:
        raise ValueError("drop_ratio must be between 0 and 1")
    if payload["no_contact_days"] < 1 or payload["min_baseline_per_day"] < 0:
        raise ValueError("no_contact_days must be positive and min_baseline_per_day non-negative")
    if payload["escalate_after_minutes"] < 1 or payload["ack_suppress_days"] < 1:
        raise ValueError("escalate_after_minutes and ack_suppress_days must be positive")


def _check_time(slot: str) -> None:
    hh, _, mm = slot.partition(":")
    if not (hh.isdigit() and mm.isdigit() and 0 <= int(hh) < 24 and 0 <= int(mm) < 60):
        raise ValueError(f"bad slot time {slot!r}; use HH:MM")


def validate_rec(payload: dict) -> None:
    if payload["capacity"] < 1 or payload["indoor_minutes"] < 1 or payload["outdoor_minutes"] < 1:
        raise ValueError("capacity and block lengths must be positive")
    if not 1 <= payload["generate_days_ahead"] <= 31:
        raise ValueError("generate_days_ahead must be between 1 and 31")
    for slot in (*payload["indoor_slots"], *payload["outdoor_slots"]):
        _check_time(slot)
    for entry in (*payload["programs"], *payload["visits"]):
        _check_time(entry["start"])
        if entry["minutes"] < 1 or entry["capacity"] < 1 or not entry["title"].strip():
            raise ValueError(
                f"program or visit {entry.get('title')!r} needs a title, minutes, capacity"
            )
        if "feature" in entry and entry["feature"] not in ALL_FEATURES:
            raise ValueError(f"unknown feature {entry['feature']!r}")


def validate_reading(payload: dict) -> None:
    ids = set()
    for it in payload["items"]:
        if it["id"] in ids or it["catalog"] not in CATALOG_FEATURE:
            raise ValueError(f"{it['id']}: duplicate id or bad catalog")
        ids.add(it["id"])
        if not it.get("source", "").strip() or not it["text"].strip():
            raise ValueError(f"{it['id']}: needs a source and some text")
        seen = {(it["language"], "standard")}
        for v in it.get("variants", []):
            key = (v.get("language"), v.get("reading_level"))
            if key[0] not in ("en", "es") or key[1] not in ("standard", "simple"):
                raise ValueError(
                    f"{it['id']}: a variant needs language en or es and a reading level"
                )
            if key in seen or not str(v.get("text", "")).strip():
                raise ValueError(f"{it['id']}: duplicate variant {key} or empty text")
            seen.add(key)


def validate_compliance(payload: dict) -> None:
    """The few compliance values that protect invariants 1 and 6 cannot be configured away."""
    if "attorney" not in (payload.get("privileged_contact_types") or []):
        raise ValueError("privileged_contact_types must include attorney (invariant 6)")
    for key in (
        "min_out_of_cell_minutes_per_day",
        "appeal_review_hours",
        "officer_weekly_immediate_sanction_cap",
        "offline_alert_minutes",
    ):
        if not isinstance(payload.get(key), int) or payload[key] < 1:
            raise ValueError(f"{key} must be a positive whole number")


def validate_chess(payload: dict) -> None:
    for key in ("queue_minutes", "moves_per_minute", "max_open_matches"):
        if not isinstance(payload.get(key), int) or payload[key] < 1:
            raise ValueError(f"chess: {key} must be a positive whole number")
    if not isinstance(payload.get("human_enabled"), bool):
        raise ValueError("chess: human_enabled must be true or false")
    if not isinstance(payload.get("disabled_units"), list):
        raise ValueError("chess: disabled_units must be a list")
    levels = payload.get("engine_levels") or []
    if [lv.get("level") for lv in levels] != list(range(1, len(levels) + 1)) or not levels:
        raise ValueError("chess: engine_levels must be numbered 1, 2, 3 ... in order")
    for lv in levels:
        if not 1 <= lv.get("depth", 0) <= 5 or not 0 <= lv.get("mistake_rate", -1) <= 1:
            raise ValueError("chess: a level needs depth 1 to 5 and mistake_rate 0 to 1")
    for key in ("handle_adjectives", "handle_nouns"):
        words = payload.get(key) or []
        if len(words) < 6 or any(not str(w).isalpha() for w in words):
            raise ValueError(f"chess: {key} needs at least six plain words")


def validate_facility(payload: dict) -> None:
    scales = payload.get("scales") or {}
    if payload.get("default_scale") not in scales:
        raise ValueError("facility: default_scale must name one of the scales")
    for name, sc in scales.items():
        for key in ("hubs", "lines_per_hub", "floors_per_line", "cells_per_floor"):
            if not isinstance(sc.get(key), int) or not 1 <= sc[key] <= 99:
                raise ValueError(f"facility: scale {name} needs {key} from 1 to 99")
    rec = payload.get("rec") or {}
    for key in (
        "rooms_per_line",
        "outdoor_rooms_per_line",
        "room_capacity",
        "max_concurrent_out_per_line",
        "stagger_minutes",
    ):
        if not isinstance(rec.get(key), int) or rec[key] < 1:
            raise ValueError(f"facility: rec.{key} must be a positive whole number")
    if rec["max_concurrent_out_per_line"] > rec["outdoor_rooms_per_line"]:
        raise ValueError("facility: max_concurrent_out_per_line cannot exceed the yards in a line")
    site = payload.get("site") or {}
    if not str(site.get("code", "")).strip() or not str(site.get("name", "")).strip():
        raise ValueError("facility: the site needs a code and a name")
