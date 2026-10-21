"""Call rules. Pure; the telephony provider and DB live elsewhere."""

import math
from dataclasses import dataclass
from datetime import datetime

PRIVILEGED_MAX_SECONDS = 3600  # safety cap only; attorney calls do not use the tier allowance


class CallDenied(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class CallPlan:
    max_seconds: int
    privileged: bool
    monitored: bool


def plan_call(
    *,
    privileged: bool,
    allowed: bool,
    limit_minutes: int | None,
    used_seconds: int,
) -> CallPlan:
    """Decide whether a call may start and for how long.

    Attorney calls are baseline: always allowed, never metered, never monitored.
    """
    if privileged:
        return CallPlan(PRIVILEGED_MAX_SECONDS, privileged=True, monitored=False)
    if not allowed or limit_minutes is None:
        raise CallDenied("FEATURE_LOCKED", "calls are locked")
    remaining = limit_minutes * 60 - used_seconds
    if remaining <= 0:
        raise CallDenied("LIMIT_REACHED", "daily call minutes used up")
    return CallPlan(remaining, privileged=False, monitored=True)


def effective_seconds(started: datetime, ended: datetime, max_seconds: int) -> int:
    """Billable length: never negative, never beyond what the plan allowed."""
    return max(0, min(int((ended - started).total_seconds()), max_seconds))


def minutes_used(seconds: int) -> int:
    return math.ceil(seconds / 60)
