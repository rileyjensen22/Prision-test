"""Validation for the jobs config section (kept outside the entitlement engine on purpose)."""


def validate_jobs(payload: dict) -> None:
    split = payload["pay_split"]
    parts = (split["resident_pct"], split["facility_pct"], split["deductions_pct"])
    if min(parts) < 0 or sum(parts) != 100:
        raise ValueError("pay_split must be non-negative percentages that add up to 100")
