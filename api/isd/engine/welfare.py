"""Welfare flags (CLAUDE.md section 11). Pure rules; each resident is compared with themselves."""

import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class WelfareRules:
    no_contact_days: int
    baseline_days: int
    recent_days: int
    drop_ratio: float
    min_baseline_per_day: float
    out_of_cell_unrecorded_days: int = 3

    @classmethod
    def from_config(cls, payload: dict) -> "WelfareRules":
        keys = cls.__dataclass_fields__
        return cls(**{k: payload[k] for k in keys if k in payload})

    @property
    def history_needed(self) -> int:
        return self.baseline_days + self.recent_days


@dataclass(frozen=True)
class WelfareFlag:
    type: str  # no_contact | usage_drop | contact_drop | out_of_cell_below | out_of_cell_unrecorded
    severity: str  # attention | info
    detail: dict


def _drop(series: Sequence[int], rules: WelfareRules) -> tuple[float, float] | None:
    """(usual, recent) daily averages if the recent days are sharply below the resident's usual."""
    baseline = series[: rules.baseline_days]
    recent = series[-rules.recent_days :]
    usual = statistics.fmean(baseline)
    now = statistics.fmean(recent)
    if usual >= rules.min_baseline_per_day and now < rules.drop_ratio * usual:
        return usual, now
    return None


def activity_flags(
    usage: Sequence[int],
    contact: Sequence[int],
    days_since_contact: int | None,
    tracked_days: int,
    rules: WelfareRules,
) -> list[WelfareFlag]:
    """Series are daily counts, oldest first, exactly `history_needed` long.

    `days_since_contact` is None when there has never been any contact. A resident without enough
    history gets no "drop" flags (there is no baseline yet) but can still get "no contact".
    """
    flags: list[WelfareFlag] = []
    never = days_since_contact is None
    gap = tracked_days if never else days_since_contact
    if gap >= rules.no_contact_days:
        flags.append(WelfareFlag("no_contact", "attention", {"days": gap, "never": never}))
    if tracked_days >= rules.history_needed:
        if (d := _drop(usage, rules)) is not None:
            flags.append(
                WelfareFlag(
                    "usage_drop", "attention", {"usual": round(d[0], 2), "recent": round(d[1], 2)}
                )
            )
        if not flags or flags[0].type != "no_contact":  # no_contact already says it
            if (d := _drop(contact, rules)) is not None:
                flags.append(
                    WelfareFlag(
                        "contact_drop",
                        "attention",
                        {"usual": round(d[0], 2), "recent": round(d[1], 2)},
                    )
                )
    return flags


def out_of_cell_flags(
    days: Sequence[tuple[date, int | None]], min_minutes: int, unrecorded_days: int
) -> list[WelfareFlag]:
    """`days` is the recent window, oldest first; None means nothing was recorded that day."""
    flags: list[WelfareFlag] = []
    below = [(d, m) for d, m in days if m is not None and m < min_minutes]
    if below:
        flags.append(
            WelfareFlag(
                "out_of_cell_below",
                "attention",
                {
                    "days": [d.isoformat() for d, _ in below],
                    "minimum": min_minutes,
                    "lowest": min(m for _, m in below),
                },
            )
        )
    trailing = 0
    for _, m in reversed(days):
        if m is not None:
            break
        trailing += 1
    if trailing >= unrecorded_days:
        flags.append(WelfareFlag("out_of_cell_unrecorded", "info", {"days": trailing}))
    return flags
