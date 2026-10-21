"""What a live mirror may show. Pure rules, enforced server-side before any frame leaves the API.

Privileged attorney communication must never be viewable (invariant 6), and legal, grievance
and health screens are sensitive in the same way, so a mirror shows only that the resident is
on a private screen, not what is on it.
"""

import re

PRIVATE_SCREEN_PREFIXES = (
    "/resident/feature/legal_materials",
    "/resident/feature/grievances_appeals",
    "/resident/feature/medical_requests",
    "/resident/feature/mental_health_requests",
    "/resident/feature/attorney_calls",
)
REDACTED_PATH = "/resident/redacted"
_SAFE_PATH = re.compile(r"^/resident(/[A-Za-z0-9_\-]+)*$")


def is_valid_screen_path(path: str) -> bool:
    return len(path) <= 100 and bool(_SAFE_PATH.match(path))


def is_private_path(path: str) -> bool:
    return any(path == p or path.startswith(p + "/") for p in PRIVATE_SCREEN_PREFIXES)


def redaction_reason(path: str | None, privileged_call_active: bool) -> str | None:
    if privileged_call_active:
        return "PRIVILEGED_CALL"
    if path is None:
        return None
    if path == REDACTED_PATH or is_private_path(path):
        return "PRIVATE_SCREEN"
    return None
