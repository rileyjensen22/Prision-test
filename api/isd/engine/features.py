"""Feature catalog. The protected baseline (invariant 1) is defined here and nowhere else."""

BASELINE_FEATURES = frozenset(
    {
        "legal_materials",
        "grievances_appeals",
        "medical_requests",
        "mental_health_requests",
        "request_staff",
        "emergency_contact",
        "religious_texts",
        "basic_education",
        "attorney_calls",
        "contact_requests",  # asking staff to approve a contact; attorney access depends on it
        "out_of_cell_minimum",
        "reentry",  # release countdown, checklist and resources: information, never lockable
    }
)

NON_BASELINE_FEATURES = frozenset(
    {
        "calls",  # non-attorney calls
        "texting",
        "video",
        "commissary",
        "chess_engine",
        "chess_human",
        "reading_general",
        "reading_expanded",
        "advanced_education",
        "outdoor_rec",
    }
)

ALL_FEATURES = BASELINE_FEATURES | NON_BASELINE_FEATURES

# Sanction scope -> features it locks. Always a subset of NON_BASELINE_FEATURES.
SCOPES: dict[str, frozenset[str]] = {
    "communication": frozenset({"calls", "texting", "video"}),
    "commissary": frozenset({"commissary"}),
    "video": frozenset({"video"}),
    "games": frozenset({"chess_human"}),  # blocks human play only; the engine stays open
    "all_non_baseline": NON_BASELINE_FEATURES,
}

APPEAL = "appeal"  # resident can file an appeal from the device
ASK_STAFF = "request_staff"  # resident can use the Request staff button
