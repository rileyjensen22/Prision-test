"""API payloads. `ResidentView` is the one payload the resident UI renders from (CLAUDE.md 9.1)."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ReasonOut(BaseModel):
    code: str
    source: str  # tier | ceiling | offense | sanction
    how_to_appeal: str  # "appeal" | "request_staff"
    ends_at: datetime | None = None
    detail: str = ""
    params: dict[str, Any] = {}
    sanction_id: int | None = None


class FeatureOut(BaseModel):
    allowed: bool
    baseline: bool
    limits: dict[str, int] = {}
    reasons: list[ReasonOut] = []


class LockOut(BaseModel):
    """One lock as the resident sees it (grouped across the features it affects)."""

    key: str
    code: str
    source: str
    features: list[str]
    ends_at: datetime | None
    detail: str
    params: dict[str, Any]
    how_to_appeal: str
    sanction_id: int | None = None
    appeal_open: bool = False


class TierOut(BaseModel):
    earned: int
    ceiling: int
    effective: int
    points: int
    next_tier: int | None  # None at tier 10
    points_to_next: int | None
    capped_by_ceiling: bool  # next tier exists but the repeat-return ceiling blocks it
    max_tier_override: int | None = None  # staff-set hard cap; None = no manual override


class AllowanceOut(BaseModel):
    feature: str
    period: str  # day | week
    unit: str
    limit: int
    used: float


class ResidentSettings(BaseModel):
    language: str
    text_size: str
    reading_level: str
    captions: bool


class UiConfig(BaseModel):
    inactivity_return_home_seconds: int


class ResidentView(BaseModel):
    resident_code: str
    settings: ResidentSettings
    tier: TierOut
    features: dict[str, FeatureOut]
    allowances: list[AllowanceOut]
    locks: list[LockOut]
    generated_at: datetime
    valid_until: datetime  # offline cache expires here; clients fail closed afterwards
    simulation: bool = False
    ui: UiConfig
    reentry: dict | None = None  # release countdown, when staff have set a date
