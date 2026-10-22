"""Keyword rules for monitored messages. Pure.

A match only ever produces a review item (invariant 12). Nothing here knows about sanctions.
"""

import re
import unicodedata


def normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", stripped).strip()


def _pattern(keyword: str) -> re.Pattern[str]:
    words = [re.escape(w) for w in normalize(keyword).split(" ") if w]
    return re.compile(r"(?<!\w)" + r"\s+".join(words) + r"(?!\w)")


def match_rules(text: str, rules: list[dict]) -> list[dict]:
    """The rules whose keywords appear as whole words or phrases, in config order."""
    haystack = normalize(text)
    return [
        rule
        for rule in rules
        if any(_pattern(k).search(haystack) for k in rule["keywords"] if normalize(k))
    ]


def validate_monitoring(payload: dict) -> None:
    if not isinstance(payload.get("text_max_chars"), int) or payload["text_max_chars"] < 1:
        raise ValueError("text_max_chars must be a positive whole number")
    seen: set[str] = set()
    for rule in payload["rules"]:
        rid = str(rule.get("id", "")).strip()
        if not rid or rid in seen:
            raise ValueError(f"rule id {rid!r} is missing or duplicated")
        seen.add(rid)
        if not str(rule.get("label", "")).strip():
            raise ValueError(f"{rid}: needs a label")
        if not [k for k in rule.get("keywords", []) if normalize(str(k))]:
            raise ValueError(f"{rid}: needs at least one keyword")
