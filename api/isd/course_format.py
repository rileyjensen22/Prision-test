"""The course format, and everything that checks it. Pure: no files, no database.

A course is a folder (see docs/courses.md):

    content/courses/NUM101/
      course.json            code, level, languages, prerequisites, lesson order, quiz settings
      quiz.json              the question bank
      lessons/<id>.<lang>.md             one Markdown file per lesson and language
      lessons/<id>.<lang>.simple.md      optional easier-reading version

`build_course` turns the parsed pieces into one dict; `validate_course_set` checks the whole
catalogue. Both collect every problem they can find, so an author sees them all at once.
"""

import re
from typing import Any

from isd.work_rules import contains_personal_data

LEVELS = ("basic", "advanced", "program")
LANGS = ("en", "es")
READING_LEVELS = ("standard", "simple")
CODE_RE = re.compile(r"^[A-Z][A-Z0-9]{2,15}$")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
MAX_LESSON_CHARS = 4000
_HTML = re.compile(r"<\s*[A-Za-z/!?]")
_LINK = re.compile(r"!?\[[^\]]*\]\([^)]*\)|https?://|www\.", re.I)
_BULLET = re.compile(r"^(?:[-*] |\d+\. )")


class CourseFormatError(ValueError):
    """Carries every problem found, one per line."""

    def __init__(self, problems: list[str]):
        super().__init__("\n".join(problems))
        self.problems = problems


def parse_lesson_markdown(text: str) -> tuple[str, str]:
    """(title, body). The first non-empty line must be `# Title`. Only paragraphs, bullet and
    numbered lists, **bold** and *italic* are allowed: no HTML, links or images, since the kiosk
    has no way out of the app."""
    lines = text.strip().splitlines()
    if not lines or not lines[0].startswith("# ") or not lines[0][2:].strip():
        raise ValueError("a lesson must start with '# Title'")
    title, body = lines[0][2:].strip(), "\n".join(lines[1:]).strip()
    if not body:
        raise ValueError("a lesson needs some text after its title")
    if len(body) > MAX_LESSON_CHARS:
        raise ValueError(f"a lesson is limited to {MAX_LESSON_CHARS} characters")
    if _HTML.search(text):
        raise ValueError("HTML is not allowed in lessons")
    if _LINK.search(text):
        raise ValueError("links and images are not allowed in lessons")
    for line in body.splitlines():
        if line.startswith("#"):
            raise ValueError("only one heading is allowed, at the top")
        if line.strip() and not (_BULLET.match(line) or line[0] not in "-*+>`|"):
            raise ValueError(f"unsupported Markdown: {line[:30]!r}")
    if contains_personal_data(text):
        raise ValueError("lesson text looks like it holds personal data")
    return title, body


def _bi(value: Any, where: str, langs: list[str], problems: list[str]) -> None:
    if not isinstance(value, dict):
        problems.append(f"{where}: expected text for each of {', '.join(langs)}")
        return
    for lang in langs:
        text = value.get(lang)
        if not isinstance(text, str) or not text.strip():
            problems.append(f"{where}: missing {lang} text")
        elif contains_personal_data(text):
            problems.append(f"{where}: {lang} text looks like it holds personal data")


def lesson_path(lesson_id: str, lang: str, level: str = "standard") -> str:
    suffix = "" if level == "standard" else f".{level}"
    return f"lessons/{lesson_id}.{lang}{suffix}.md"


def build_course(manifest: dict, files: dict[str, str], quiz: dict, folder: str = "") -> dict:
    """Assembles a course from its manifest, lesson files and quiz bank, or raises
    CourseFormatError listing every problem."""
    tag = f"{folder or manifest.get('code', '?')}"
    problems: list[str] = []

    def bad(msg: str) -> None:
        problems.append(f"{tag}: {msg}")

    code = manifest.get("code", "")
    if not isinstance(code, str) or not CODE_RE.match(code):
        bad("code must be 3 to 16 capital letters or digits, starting with a letter")
    if manifest.get("level") not in LEVELS:
        bad(f"level must be one of {', '.join(LEVELS)}")
    langs = manifest.get("languages") or []
    if not langs or "en" not in langs or any(lang not in LANGS for lang in langs):
        bad("languages must include en and may add es")
        langs = [lang for lang in langs if lang in LANGS] or ["en"]
    levels = manifest.get("reading_levels") or ["standard"]
    if "standard" not in levels or any(r not in READING_LEVELS for r in levels):
        bad("reading_levels must include standard and may add simple")
        levels = [r for r in levels if r in READING_LEVELS] or ["standard"]
    mark = manifest.get("pass_mark")
    if not isinstance(mark, (int, float)) or not 0 < mark <= 1:
        bad("pass_mark must be above 0 and at most 1")
    _bi(manifest.get("title"), f"{tag} title", langs, problems)
    if manifest.get("summary") is not None:
        _bi(manifest["summary"], f"{tag} summary", langs, problems)
    prereqs = manifest.get("prerequisites", [])
    if not isinstance(prereqs, list) or code in prereqs or len(set(prereqs)) != len(prereqs):
        bad("prerequisites must be a list of other course codes, each once")
        prereqs = []

    lessons = []
    ids = manifest.get("lessons") or []
    if (
        not ids
        or len(set(ids)) != len(ids)
        or not all(isinstance(i, str) and ID_RE.match(i) for i in ids)
    ):
        bad("lessons must be a non-empty list of distinct ids (lowercase letters, digits, dashes)")
        ids = []
    for lid in ids:
        titles: dict[str, str] = {}
        bodies: dict[str, dict[str, str]] = {}
        for level in levels:
            for lang in langs:
                path = lesson_path(lid, lang, level)
                if path not in files:
                    bad(f"missing file {path}")
                    continue
                try:
                    title, body = parse_lesson_markdown(files[path])
                except ValueError as e:
                    bad(f"{path}: {e}")
                    continue
                if level == "standard":
                    titles[lang] = title
                bodies.setdefault(level, {})[lang] = body
        lessons.append({"id": lid, "title": titles, "body": bodies})
    declared = {lesson_path(i, lang, lv) for i in ids for lang in langs for lv in levels}
    for path in sorted(set(files) - declared):
        bad(f"{path} is not used by any lesson, language or reading level in course.json")

    bank = quiz.get("questions") if isinstance(quiz, dict) else None
    questions = _check_bank(bank, langs, tag, problems)
    settings = manifest.get("quiz") or {}
    draw = settings.get("draw")
    if draw is not None and (not isinstance(draw, int) or not 1 <= draw <= len(questions)):
        bad(
            f"quiz.draw must be a whole number from 1 to the {len(questions)} questions in the bank"
        )
    for key in ("max_attempts", "cooldown_minutes"):
        if key in settings and (not isinstance(settings[key], int) or settings[key] < 1):
            bad(f"quiz.{key} must be a positive whole number")
    if problems:
        raise CourseFormatError(problems)
    return {
        "code": code,
        "level": manifest["level"],
        "title": manifest["title"],
        "summary": manifest.get("summary"),
        "languages": langs,
        "reading_levels": levels,
        "pass_mark": mark,
        "prerequisites": prereqs,
        "points_kind": manifest.get("points_kind"),
        "license": manifest.get("license", ""),
        "lessons": lessons,
        "quiz": {**settings, "bank": questions},
    }


def _check_bank(bank: Any, langs: list[str], tag: str, problems: list[str]) -> list[dict]:
    if not isinstance(bank, list) or not bank:
        problems.append(f"{tag}: quiz.json needs a non-empty 'questions' list")
        return []
    seen: set[str] = set()
    for q in bank:
        qid = q.get("id") if isinstance(q, dict) else None
        where = f"{tag} question {qid!r}"
        if not isinstance(qid, str) or not ID_RE.match(qid) or qid in seen:
            problems.append(f"{where}: id missing, malformed or repeated")
            continue
        seen.add(qid)
        _bi(q.get("prompt"), f"{where} prompt", langs, problems)
        choices = q.get("choices")
        if not isinstance(choices, list) or not 2 <= len(choices) <= 6:
            problems.append(f"{where}: needs 2 to 6 choices")
            continue
        for i, choice in enumerate(choices):
            _bi(choice, f"{where} choice {i + 1}", langs, problems)
        texts = [str(c.get("en", "")).strip().casefold() for c in choices if isinstance(c, dict)]
        if len(set(texts)) != len(texts):
            problems.append(f"{where}: two choices are the same")
        if not isinstance(q.get("answer"), int) or not 0 <= q["answer"] < len(choices):
            problems.append(f"{where}: answer must be the number of a choice (starting at 0)")
    return bank


def validate_course_set(courses: list[dict], settings: dict) -> None:
    """Checks the catalogue as a whole; raises CourseFormatError with every problem."""
    problems: list[str] = []
    by_code: dict[str, dict] = {}
    for c in courses:
        if c["code"] in by_code:
            problems.append(f"{c['code']}: this code is used by more than one course")
        by_code[c["code"]] = c
    kinds = set(settings.get("points_by_level", {}).values())
    if set(settings.get("points_by_level", {})) != set(LEVELS):
        problems.append("settings: points_by_level needs a points kind for each level")
    for c in courses:
        if c.get("points_kind") and c["points_kind"] not in settings.get(
            "known_point_kinds", kinds
        ):
            problems.append(f"{c['code']}: unknown points_kind {c['points_kind']!r}")
        for p in c["prerequisites"]:
            if p not in by_code:
                problems.append(f"{c['code']}: prerequisite {p} is not a course")
            elif c["level"] == "basic" and by_code[p]["level"] != "basic":
                problems.append(
                    f"{c['code']}: a basic course may only require basic courses, so basic "
                    "education is always a way up"
                )
    if courses and not any(c["level"] == "basic" and not c["prerequisites"] for c in courses):
        problems.append("at least one basic course must have no prerequisites")
    problems += _cycles(by_code)
    if problems:
        raise CourseFormatError(problems)


def _cycles(by_code: dict[str, dict]) -> list[str]:
    state: dict[str, int] = {}
    out: list[str] = []

    def visit(code: str, path: list[str]) -> None:
        if state.get(code) == 2 or code not in by_code:
            return
        if state.get(code) == 1:
            out.append(
                "prerequisites go in a circle: " + " -> ".join([*path[path.index(code) :], code])
            )
            return
        state[code] = 1
        for p in by_code[code]["prerequisites"]:
            visit(p, [*path, code])
        state[code] = 2

    for code in sorted(by_code):
        visit(code, [])
    return out
