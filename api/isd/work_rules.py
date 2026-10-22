"""Rules for work tasks and pay. Pure: no database, no provider.

Kept outside the entitlement engine on purpose: work never affects tier or entitlements
(invariant 7). Task content is limited to public or synthetic material, and anything that looks
like personal data is refused on the way in (tasks) and on the way back (answers).
"""

import difflib
import re
from dataclasses import dataclass

TASK_KINDS = ("transcription_public_domain", "captioning", "labeling_non_personal")

_PATTERNS = (
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),  # email
    re.compile(r"(?<!\d)(?:\+?1[ .-]?)?\(?\d{3}\)?[ .-]?\d{3}[ .-]?\d{4}(?!\d)"),  # phone
    re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)"),  # US social security number
    re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)"),  # card-like digit run
    re.compile(
        r"\b\d{1,5}\s+[A-Za-z0-9.' ]{2,30}\s(?:street|st|avenue|ave|road|rd|drive|dr|lane|ln"
        r"|boulevard|blvd|court|ct)\b",
        re.I,
    ),  # street address
    re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b"),  # a full date such as a birth date
)


def contains_personal_data(text: str) -> bool:
    return any(p.search(text) for p in _PATTERNS)


def split_pay(
    gross_cents: int, resident_pct: int, facility_pct: int, deductions_pct: int
) -> tuple[int, int, int]:
    """(resident, facility, deductions) in whole cents. Facility and deductions round down and
    the remainder goes to the resident, so the parts always add up to the gross."""
    if min(resident_pct, facility_pct, deductions_pct) < 0 or (
        resident_pct + facility_pct + deductions_pct != 100
    ):
        raise ValueError("the split must be non-negative percentages that add up to 100")
    facility = gross_cents * facility_pct // 100
    deductions = gross_cents * deductions_pct // 100
    return gross_cents - facility - deductions, facility, deductions


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.casefold()).strip()


def similarity(a: str, b: str) -> float:
    a, b = normalize(a), normalize(b)
    if a == b:
        return 1.0
    return difflib.SequenceMatcher(None, a, b).ratio()


@dataclass(frozen=True)
class Review:
    accepted: bool
    reason: str  # ACCEPTED or a short code


_REQUIRED = {
    "transcription_public_domain": ("scan", "expected", "source"),
    "captioning": ("scene", "keywords", "source"),
    "labeling_non_personal": ("item", "options", "expected", "source"),
}
_HIDDEN = {"expected", "keywords"}  # what the device is never sent


def _strings(spec: dict) -> list[str]:
    out: list[str] = []
    for value in spec.values():
        if isinstance(value, str):
            out.append(value)
        elif isinstance(value, list):
            out.extend(str(v) for v in value)
    return out


def validate_task_spec(kind: str, spec: dict) -> None:
    if kind not in _REQUIRED:
        raise ValueError(f"task kind must be one of {', '.join(TASK_KINDS)}")
    missing = [k for k in _REQUIRED[kind] if not spec.get(k)]
    if missing:
        raise ValueError(f"task is missing {', '.join(missing)}")
    if any(contains_personal_data(s) for s in _strings(spec)):
        raise ValueError("task content looks like it holds personal data")
    if kind == "labeling_non_personal" and spec["expected"] not in spec["options"]:
        raise ValueError("the expected label must be one of the options")


def public_view(kind: str, spec: dict) -> dict:
    return {k: v for k, v in spec.items() if k not in _HIDDEN}


def review_answer(kind: str, spec: dict, answer: str, min_similarity: float) -> Review:
    answer = answer.strip()
    if not answer:
        return Review(False, "EMPTY")
    if contains_personal_data(answer):
        return Review(False, "PERSONAL_DATA")
    if kind == "transcription_public_domain":
        ok = similarity(answer, spec["expected"]) >= min_similarity
        return Review(ok, "ACCEPTED" if ok else "TOO_DIFFERENT")
    if kind == "captioning":
        words = normalize(answer).split(" ")
        if not 3 <= len(words) <= 30 or len(answer) > 140:
            return Review(False, "BAD_LENGTH")
        hit = any(normalize(k) in normalize(answer) for k in spec["keywords"])
        return Review(hit, "ACCEPTED" if hit else "OFF_TOPIC")
    ok = answer == spec["expected"]
    return Review(ok, "ACCEPTED" if ok else "WRONG_LABEL")
