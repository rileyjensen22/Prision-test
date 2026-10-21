"""Repeat-return ceiling (CLAUDE.md 4.4). Pure math, no I/O."""


def raw_loss(n: int, N: float = 12, p: float = 1.5) -> float:
    """Unrounded tiers lost after n prior returns."""
    return 10 * (max(n, 0) / N) ** p


def ceiling_tier(n: int, N: float = 12, p: float = 1.5) -> int:
    return max(1, min(10, round(10 * (1 - (max(n, 0) / N) ** p))))
