"""Earned-tier evaluation: promotion by points, hysteresis, at most one drop per 7 days."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from isd.engine.config import EngineConfig

MAX_TIER = 10
DROP_WINDOW = timedelta(days=7)


@dataclass(frozen=True)
class TierDecision:
    tier: int
    direction: str  # up | down | same


def tier_for_points(points: int, thresholds: tuple[int, ...]) -> int:
    """Highest tier whose promotion threshold is met (no hysteresis)."""
    return max(1, sum(1 for th in thresholds if points >= th))


def demotion_threshold(tier: int, cfg: EngineConfig) -> float:
    """Points below which `tier` is lost. Sits under the promotion threshold (hysteresis)."""
    return cfg.thresholds[tier - 1] * (1 - cfg.hysteresis)


def evaluate_tier(
    current: int, points: int, cfg: EngineConfig, last_drop_at: datetime | None, now: datetime
) -> TierDecision:
    tier = current
    while tier < MAX_TIER and points >= cfg.thresholds[tier]:
        tier += 1
    if tier > current:
        return TierDecision(tier, "up")
    can_drop = last_drop_at is None or now - last_drop_at >= DROP_WINDOW
    if current > 1 and points < demotion_threshold(current, cfg) and can_drop:
        return TierDecision(current - 1, "down")  # never more than one level at a time
    return TierDecision(current, "same")
