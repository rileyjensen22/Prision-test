import copy

import pytest
from hypothesis import given
from hypothesis import strategies as st

from isd.course_format import (
    CourseFormatError,
    build_course,
    lesson_path,
    parse_lesson_markdown,
    validate_course_set,
)

MANIFEST = {
    "code": "NUM101",
    "level": "basic",
    "languages": ["en", "es"],
    "reading_levels": ["standard", "simple"],
    "title": {"en": "Everyday Numbers", "es": "Números de todos los días"},
    "pass_mark": 0.6,
    "prerequisites": [],
    "lessons": ["place-value"],
    "quiz": {"draw": 2},
}
FILES = {
    lesson_path(
        "place-value", lang, level
    ): f"# Place value {lang} {level}\n\nEach digit has a value."
    for lang in ("en", "es")
    for level in ("standard", "simple")
}
QUIZ = {
    "questions": [
        {
            "id": f"q{i}",
            "prompt": {"en": f"Question {i}?", "es": f"¿Pregunta {i}?"},
            "choices": [
                {"en": "Yes", "es": "Sí"},
                {"en": "No", "es": "No"},
            ],
            "answer": 0,
        }
        for i in (1, 2, 3)
    ]
}


def build(**changes):
    m, f, q = copy.deepcopy(MANIFEST), copy.deepcopy(FILES), copy.deepcopy(QUIZ)
    m.update(changes.pop("manifest", {}))
    f.update(changes.pop("files", {}))
    for path in changes.pop("drop", []):
        f.pop(path)
    q = changes.pop("quiz", q)
    return build_course(m, f, q, "NUM101")


def problems(**changes) -> list[str]:
    with pytest.raises(CourseFormatError) as e:
        build(**changes)
    return e.value.problems


def test_a_well_formed_course_builds_with_every_language_and_reading_level():
    c = build()
    assert c["code"] == "NUM101" and c["languages"] == ["en", "es"]
    lesson = c["lessons"][0]
    assert lesson["title"] == {"en": "Place value en standard", "es": "Place value es standard"}
    assert set(lesson["body"]) == {"standard", "simple"} and set(lesson["body"]["simple"]) == {
        "en",
        "es",
    }
    assert len(c["quiz"]["bank"]) == 3 and c["quiz"]["draw"] == 2


def test_markdown_rules():
    assert parse_lesson_markdown("# Title\n\nA **bold** word.\n\n- one\n- two\n\n1. first") == (
        "Title",
        "A **bold** word.\n\n- one\n- two\n\n1. first",
    )
    for text, why in (
        ("No heading\n\ntext", "must start"),
        ("# Title", "some text"),
        ("# Title\n\n<script>x</script>", "HTML"),
        ("# Title\n\nsee [this](http://example.com)", "links"),
        ("# Title\n\nvisit www.example.com", "links"),
        ("# Title\n\n## Another\n\ntext", "one heading"),
        ("# Title\n\n> quoted", "unsupported"),
        ("# Title\n\ncall 404-555-0134 now", "personal"),
        ("# Title\n\n" + "x" * 4001, "limited"),
    ):
        with pytest.raises(ValueError, match=why):
            parse_lesson_markdown(text)


@given(st.text(max_size=300))
def test_the_markdown_parser_never_crashes(text):
    try:
        parse_lesson_markdown(text)
    except ValueError:
        pass


def test_every_problem_is_reported_not_just_the_first():
    found = problems(
        manifest={"level": "expert", "pass_mark": 2, "code": "bad"},
        drop=[lesson_path("place-value", "es", "simple")],
        files={lesson_path("place-value", "en"): "no heading"},
    )
    text = "\n".join(found)
    for needle in ("code must be", "level must be", "pass_mark", "missing file", "must start with"):
        assert needle in text


def test_a_declared_language_must_be_complete_and_stray_files_are_caught():
    assert any(
        "missing file lessons/place-value.es.md" in p
        for p in problems(drop=["lessons/place-value.es.md"])
    )
    assert any(
        "not used by any lesson" in p
        for p in problems(files={"lessons/ghost.en.md": "# G\n\ntext"})
    )
    spanish_title_missing = {"title": {"en": "Only English"}}
    assert any("missing es text" in p for p in problems(manifest=spanish_title_missing))


def test_quiz_banks_are_checked_question_by_question():
    def with_question(**q):
        bad = copy.deepcopy(QUIZ)
        bad["questions"][0].update(q)
        return problems(quiz=bad)

    assert any("answer must be" in p for p in with_question(answer=5))
    assert any("2 to 6 choices" in p for p in with_question(choices=[{"en": "x", "es": "x"}]))
    assert any(
        "two choices are the same" in p
        for p in with_question(choices=[{"en": "Same", "es": "A"}, {"en": "same", "es": "B"}])
    )
    assert any("missing es text" in p for p in with_question(prompt={"en": "Only English?"}))
    dup = copy.deepcopy(QUIZ)
    dup["questions"][1]["id"] = "q1"
    assert any("repeated" in p for p in problems(quiz=dup))
    assert any("non-empty" in p for p in problems(quiz={"questions": []}))
    assert any("quiz.draw" in p for p in problems(manifest={"quiz": {"draw": 9}}))
    assert any(
        "max_attempts" in p for p in problems(manifest={"quiz": {"draw": 2, "max_attempts": 0}})
    )


def test_personal_data_anywhere_in_a_course_is_refused():
    leaky = copy.deepcopy(QUIZ)
    leaky["questions"][0]["prompt"]["en"] = "Email pat@example.com about it?"
    assert any("personal data" in p for p in problems(quiz=leaky))


def course(code, level="basic", prereqs=()):
    return {"code": code, "level": level, "prerequisites": list(prereqs), "points_kind": None}


SETTINGS = {
    "points_by_level": {
        "basic": "basic_course",
        "advanced": "advanced_course",
        "program": "program_certificate",
    }
}


def test_the_catalogue_needs_a_way_up_and_no_circles_or_missing_prerequisites():
    validate_course_set([course("A"), course("B", "advanced", ["A"])], SETTINGS)
    cases = (
        ([course("A"), course("A")], "more than one"),
        ([course("A", prereqs=["ZZ"])], "not a course"),
        ([course("A", "advanced"), course("B", "advanced", ["A"])], "no prerequisites"),
        ([course("A"), course("B", prereqs=["C"]), course("C", prereqs=["B"])], "circle"),
        ([course("A"), course("B", "advanced"), course("C", prereqs=["B"])], "only require basic"),
    )
    for courses, needle in cases:
        with pytest.raises(CourseFormatError, match=needle):
            validate_course_set(courses, SETTINGS)
    with pytest.raises(CourseFormatError, match="points_by_level"):
        validate_course_set([course("A")], {"points_by_level": {"basic": "basic_course"}})
