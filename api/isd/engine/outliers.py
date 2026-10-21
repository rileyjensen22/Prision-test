"""Officer outlier detection (CLAUDE.md section 6). Pure statistics, no I/O.

Each staff member is compared with their same-role peers, leaving themselves out of the
baseline so one extreme person cannot hide by inflating the spread. Only unusually HIGH
values are flagged: this view exists to surface possible over-reporting or over-sanctioning.
"""

import statistics
from dataclasses import dataclass

COUNT_METRICS = ("reports", "sanctions")
RATE_METRICS = ("overturn_rate", "rejection_rate")
# Smallest spread we treat as meaningful, so a peer group of identical numbers does not make
# a one-unit difference look infinite.
STD_FLOOR = {"reports": 1.0, "sanctions": 1.0, "overturn_rate": 0.1, "rejection_rate": 0.1}


@dataclass(frozen=True)
class StaffStats:
    reports: int  # sanctions this person issued (any outcome)
    sanctions: int  # of those, applied to the resident (active or later overturned)
    overturned: int  # of those, overturned on appeal
    rejected: int  # of those, rejected by a supervisor


@dataclass(frozen=True)
class Flag:
    metric: str
    value: float
    peer_mean: float
    z: float


def metrics_for(s: StaffStats, min_count: int) -> dict[str, float | None]:
    return {
        "reports": float(s.reports),
        "sanctions": float(s.sanctions),
        # rates need enough volume to mean anything
        "overturn_rate": s.overturned / s.sanctions if s.sanctions >= min_count else None,
        "rejection_rate": s.rejected / s.reports if s.reports >= min_count else None,
    }


def find_outliers(
    stats: dict[str, StaffStats],
    *,
    z_threshold: float = 2.0,
    min_peers: int = 3,
    min_count: int = 3,
) -> dict[str, list[Flag]]:
    """Returns flags per person (empty list when none). Groups must already be same-role."""
    metrics = {k: metrics_for(v, min_count) for k, v in stats.items()}
    out: dict[str, list[Flag]] = {k: [] for k in stats}
    for who in stats:
        for metric in (*COUNT_METRICS, *RATE_METRICS):
            value = metrics[who][metric]
            peers = [m[metric] for k, m in metrics.items() if k != who and m[metric] is not None]
            if value is None or len(peers) < min_peers:
                continue
            if metric in COUNT_METRICS and value < min_count:
                continue
            mean = statistics.fmean(peers)
            std = max(statistics.pstdev(peers), STD_FLOOR[metric])
            z = (value - mean) / std
            if z >= z_threshold:
                out[who].append(Flag(metric, value, mean, round(z, 2)))
    return out
