"""Out-of-cell movement: turning tap-out and tap-in events into time. Pure.

Time is only ever counted between a tap-out and the next tap-in. A stray tap-in (not out) or a
second tap-out (already out) is ignored rather than inventing time.
"""

from collections.abc import Sequence
from datetime import date, datetime, time, timedelta

Interval = tuple[datetime, datetime]


def pair_events(events: Sequence[tuple[str, datetime]]) -> tuple[list[Interval], datetime | None]:
    """(closed intervals, when the current open interval began or None). Events oldest first."""
    closed: list[Interval] = []
    since: datetime | None = None
    for kind, when in events:
        if kind == "out" and since is None:
            since = when
        elif kind == "in" and since is not None:
            if when > since:
                closed.append((since, when))
            since = None
    return closed, since


def close_intervals(events: Sequence[tuple[str, datetime]], now: datetime) -> list[Interval]:
    closed, since = pair_events(events)
    if since is not None and now > since:
        closed.append((since, now))
    return closed


def _minutes(a: datetime, b: datetime) -> int:
    return int((b - a).total_seconds() // 60)


def minutes_by_day(intervals: Sequence[Interval]) -> dict[date, int]:
    """Whole minutes per calendar day; an interval across midnight is split."""
    out: dict[date, int] = {}
    for start, end in intervals:
        cursor = start
        while cursor < end:
            midnight = datetime.combine(
                cursor.date() + timedelta(days=1), time.min, tzinfo=cursor.tzinfo
            )
            piece_end = min(end, midnight)
            out[cursor.date()] = out.get(cursor.date(), 0) + _minutes(cursor, piece_end)
            cursor = piece_end
    return out


def overlap_minutes(intervals: Sequence[Interval], window: Interval) -> int:
    """Minutes inside `window`, counting overlapping intervals only once."""
    clipped = sorted(
        (max(s, window[0]), min(e, window[1]))
        for s, e in intervals
        if s < window[1] and e > window[0]
    )
    total, reach = 0, None
    for s, e in clipped:
        if reach is not None and s < reach:
            s = reach
        if e > s:
            total += _minutes(s, e)
            reach = e if reach is None else max(reach, e)
    return total


def attendance(intervals: Sequence[Interval], window: Interval, now: datetime) -> str:
    """upcoming | in_progress | attended | partial | missed for a booked block."""
    got = overlap_minutes(intervals, window)
    length = max(1, _minutes(*window))
    if now < window[0]:
        return "upcoming"
    if got * 2 >= length:
        return "attended"
    if now < window[1]:
        return "in_progress"
    return "partial" if got > 0 else "missed"
