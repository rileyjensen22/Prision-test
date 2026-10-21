"""Allowance periods. Day/week boundaries are UTC; a facility time zone is a later config item."""

from datetime import datetime, timedelta


def period_start(now: datetime, period: str) -> datetime:
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "day":
        return midnight
    if period == "week":  # ISO week, Monday start
        return midnight - timedelta(days=midnight.weekday())
    raise ValueError(f"unknown period {period!r}")
