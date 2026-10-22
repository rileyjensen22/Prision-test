"""Validation for the jobs config section (kept outside the entitlement engine on purpose)."""

from isd.engine.features import SCOPES


def validate_jobs(payload: dict) -> None:
    split = payload["pay_split"]
    parts = (split["resident_pct"], split["facility_pct"], split["deductions_pct"])
    if min(parts) < 0 or sum(parts) != 100:
        raise ValueError("pay_split must be non-negative percentages that add up to 100")
    if not isinstance(payload["suspend_on_sanction"], bool):
        raise ValueError("suspend_on_sanction must be true or false")
    if unknown := set(payload["suspend_scopes"]) - set(SCOPES):
        raise ValueError(f"unknown sanction scopes: {sorted(unknown)}")
    for key in ("max_tasks_per_day", "claim_minutes", "min_payout_cents"):
        if not isinstance(payload[key], int) or payload[key] < 1:
            raise ValueError(f"{key} must be a positive whole number")
    if not 0 < payload["accept_similarity"] <= 1:
        raise ValueError("accept_similarity must be above 0 and at most 1")
