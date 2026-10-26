"""Reading rules with no I/O: catalogs, pagination, progress."""

import re

CATALOG_FEATURE = {
    "general": "reading_general",
    "expanded": "reading_expanded",
    "legal": "legal_materials",
    "religious": "religious_texts",
}
# These map to protected-baseline features (invariant 1): never locked, never allow-listed away.
BASELINE_CATALOGS = frozenset({"legal", "religious"})

_SENTENCE = re.compile(r"(?<=[.!?])\s+")


def _split_long(paragraph: str, max_chars: int) -> list[str]:
    pages: list[str] = []
    current = ""
    for sentence in _SENTENCE.split(paragraph):
        while len(sentence) > max_chars:  # a single enormous sentence: cut on a space
            cut = sentence.rfind(" ", 0, max_chars)
            if cut <= 0:
                cut = max_chars
            head, sentence = sentence[:cut].strip(), sentence[cut:].strip()
            if current:
                pages.append(current)
                current = ""
            if head:
                pages.append(head)
        if not sentence:
            continue
        if current and len(current) + 1 + len(sentence) > max_chars:
            pages.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        pages.append(current)
    return pages


def paginate(text: str, max_chars: int = 500) -> list[str]:
    """Blank lines separate pages; a paragraph longer than `max_chars` is split on sentences."""
    pages: list[str] = []
    for paragraph in re.split(r"\n\s*\n", text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        pages.extend(
            [paragraph] if len(paragraph) <= max_chars else _split_long(paragraph, max_chars)
        )
    return pages


def clamp_page(page: int, total: int) -> int:
    return max(0, min(page, total - 1))


def is_complete(page: int, total: int) -> bool:
    return total > 0 and page >= total - 1


LEVELS = ("standard", "simple")


def pick_variant(item: dict, language: str, level: str) -> dict:
    """The text of `item` that best fits a resident's language and reading level.

    Order: same language and level, same language at the standard level, English at the same level,
    then the item's own text. Returns title, author, text, language and the level actually used, so
    the screen can show what the resident really got. Pure; no database."""
    level = level if level in LEVELS else "standard"
    base = {
        "title": item["title"],
        "author": item["author"],
        "text": item["text"],
        "language": item["language"],
        "reading_level": "standard",
    }
    options = {(item["language"], "standard"): base}
    for v in item.get("variants", []):
        options[(v["language"], v["reading_level"])] = {
            "title": v.get("title", item["title"]),
            "author": v.get("author", item["author"]),
            "text": v["text"],
            "language": v["language"],
            "reading_level": v["reading_level"],
        }
    for key in ((language, level), (language, "standard"), ("en", level), ("en", "standard")):
        if key in options:
            return options[key]
    return base
