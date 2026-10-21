"""Commissary rules. Money is integer cents. Pure; the ledger lives in services."""

MAX_QTY_PER_LINE = 20


class OrderError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def item_block_reason(item: dict, effective_tier: int, offenses: tuple[str, ...]) -> str | None:
    if effective_tier < item["min_tier"]:
        return "ITEM_TIER"
    if set(item["blocked_offense_categories"]) & set(offenses):
        return "ITEM_OFFENSE"
    return None


def price_order(lines: dict[str, int], catalog: dict[str, dict]) -> int:
    if not lines:
        raise OrderError("EMPTY_ORDER", "no items")
    total = 0
    for code, qty in lines.items():
        if code not in catalog:
            raise OrderError("UNKNOWN_ITEM", f"unknown item {code}")
        if not 1 <= qty <= MAX_QTY_PER_LINE:
            raise OrderError("BAD_QUANTITY", f"quantity for {code} must be 1..{MAX_QTY_PER_LINE}")
        total += catalog[code]["price_cents"] * qty
    return total


def check_order(total: int, balance: int, weekly_limit: int, spent_this_week: int) -> None:
    if total > balance:
        raise OrderError("INSUFFICIENT_FUNDS", "not enough money in your account")
    if spent_this_week + total > weekly_limit:
        raise OrderError("WEEKLY_LIMIT", "this would pass your weekly spending limit")
