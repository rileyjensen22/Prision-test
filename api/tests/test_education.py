"""Phase 14: prerequisites, save and resume, randomised quizzes with paced attempts, reading
levels, certificates, points mapping, and adding a course with no code change."""

import json
import random
import shutil
import tempfile
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from isd.config_loader import load_config
from isd.course_format import CourseFormatError
from isd.courses_loader import COURSES_DIR, load_course_folder, load_courses
from isd.models import Certificate, PointEvent, QuizAttempt, QuizSession, Resident
from isd.services import education, points
from isd.services.audit import SYSTEM
from isd.services.config_store import get_current, set_config
from isd.services.education import EducationError
from tests.conftest import NOW
from tests.helpers import quiz_answers, take_quiz


def learn(owner, rid, code, now=NOW):
    for le in education.get_course(owner, rid, code, now)["lessons"]:
        education.complete_lesson(owner, rid, code, le["id"], now)


def finish(owner, rid, code, now=NOW):
    learn(owner, rid, code, now)
    return take_quiz(owner, rid, code, now)


def give(owner, rid, n):
    points.record_points(
        owner, SYSTEM, rid, "seed_adjustment", n, "system", NOW - timedelta(days=1)
    )
    points.evaluate_tier(owner, rid, NOW)


# ---------------- the shipped catalogue ----------------
def test_the_seed_catalogue_covers_the_subjects_and_has_spanish_and_easier_reading():
    courses = {c["code"]: c for c in load_courses(COURSES_DIR)}
    assert 5 <= len(courses) <= 8
    spanish = [c for c in courses.values() if "es" in c["languages"]]
    assert len(spanish) >= 2
    easier = [c for c in courses.values() if "simple" in c["reading_levels"]]
    assert easier
    assert {c["level"] for c in courses.values()} == {"basic", "advanced", "program"}
    assert all(c["license"] for c in courses.values())  # every course says where it came from
    assert all(len(c["quiz"]["bank"]) >= c["quiz"].get("draw", 5) for c in courses.values())


def test_basic_education_is_always_a_way_up():
    courses = load_courses(COURSES_DIR)
    basic = [c for c in courses if c["level"] == "basic"]
    assert any(not c["prerequisites"] for c in basic)
    assert all(
        all(p in {b["code"] for b in basic} for p in c["prerequisites"]) for c in basic
    )  # a basic course only ever needs other basic courses


# ---------------- prerequisites ----------------
def test_a_course_waits_for_its_prerequisites_and_says_which(owner, seeded, make_resident):
    rid = make_resident()
    give(owner, rid, 300)  # tier 3: advanced courses are open
    listing = {c["code"]: c for c in education.list_courses(owner, rid, NOW)}
    assert listing["JOBS101"]["allowed"] is False and listing["JOBS101"]["missing"] == ["LIT101"]
    assert listing["JOBS101"]["reasons"][0]["code"] == "PREREQUISITE"
    assert listing["JOBS101"]["missing_titles"]["LIT101"]["en"] == "Reading Basics"
    assert listing["LIT101"]["allowed"] and listing["NUM101"]["allowed"]
    with pytest.raises(EducationError) as e:
        education.get_course(owner, rid, "JOBS101", NOW)
    assert e.value.code == "PREREQ_MISSING" and e.value.extra["missing"] == ["LIT101"]
    with pytest.raises(EducationError):
        education.complete_lesson(owner, rid, "JOBS101", "resume", NOW)
    finish(owner, rid, "LIT101")
    assert education.get_course(owner, rid, "JOBS101", NOW)["code"] == "JOBS101"


def test_a_program_needs_every_prerequisite(owner, seeded, make_resident):
    rid = make_resident()
    give(owner, rid, 300)
    for code in ("LIT101", "JOBS101", "MONEY101"):
        finish(owner, rid, code)
    with pytest.raises(EducationError) as e:
        education.get_course(owner, rid, "REENTRY301", NOW)
    assert e.value.extra["missing"] == ["CREDIT201"]  # one of the two is still missing
    finish(owner, rid, "CREDIT201")
    assert education.get_course(owner, rid, "REENTRY301", NOW)["level"] == "program"


# ---------------- save and resume ----------------
def test_lessons_are_remembered_and_finishing_one_twice_is_harmless(owner, seeded, make_resident):
    rid = make_resident()
    lessons = [le["id"] for le in education.get_course(owner, rid, "MONEY101", NOW)["lessons"]]
    assert education.get_course(owner, rid, "MONEY101", NOW)["last_lesson"] is None
    education.complete_lesson(owner, rid, "MONEY101", lessons[0], NOW)
    education.complete_lesson(owner, rid, "MONEY101", lessons[0], NOW)  # a replayed offline event
    education.complete_lesson(owner, rid, "MONEY101", lessons[1], NOW + timedelta(minutes=1))
    resumed = education.get_course(owner, rid, "MONEY101", NOW + timedelta(hours=5))
    assert resumed["lessons_done"] == lessons[:2] and resumed["last_lesson"] == lessons[1]
    with pytest.raises(EducationError) as e:
        education.complete_lesson(owner, rid, "MONEY101", "no-such-lesson", NOW)
    assert e.value.code == "NOT_FOUND"


# ---------------- randomised quizzes ----------------
def test_each_attempt_is_a_different_paper_even_when_the_whole_bank_is_used(
    owner, seeded, make_resident
):
    rid = make_resident()
    learn(owner, rid, "MONEY101")  # a bank of 5, all 5 are asked
    first = education.start_quiz(owner, rid, "MONEY101", NOW, random.Random(1))
    take = quiz_answers(owner, first["quiz_id"], "MONEY101", correct=False)
    education.submit_quiz(owner, rid, "MONEY101", first["quiz_id"], take, NOW)
    second = education.start_quiz(
        owner, rid, "MONEY101", NOW + timedelta(minutes=11), random.Random(2)
    )
    order = lambda p: [q["id"] for q in p["questions"]]  # noqa: E731
    shown = lambda p: [[c["en"] for c in q["choices"]] for q in p["questions"]]  # noqa: E731
    assert sorted(order(first)) == sorted(order(second))
    assert order(first) != order(second) or shown(first) != shown(second)


def test_a_larger_bank_gives_a_different_selection(owner, seeded, make_resident):
    rid = make_resident()
    learn(owner, rid, "NUM101")
    papers = []
    for i in range(4):
        p = education.start_quiz(
            owner, rid, "NUM101", NOW + timedelta(hours=i * 2), random.Random(i)
        )
        assert len(p["questions"]) == 4
        papers.append(frozenset(q["id"] for q in p["questions"]))
        education.submit_quiz(
            owner,
            rid,
            "NUM101",
            p["quiz_id"],
            quiz_answers(owner, p["quiz_id"], "NUM101", correct=False),
            NOW + timedelta(hours=i * 2),
        )
    assert len(set(papers)) > 1


def test_the_right_answer_is_not_always_in_the_same_place(owner, seeded, make_resident):
    rid = make_resident()
    learn(owner, rid, "MONEY101")
    positions = set()
    for i in range(12):
        paper = education.start_quiz(
            owner, rid, "MONEY101", NOW + timedelta(days=i), random.Random(i)
        )
        positions |= set(quiz_answers(owner, paper["quiz_id"], "MONEY101"))
        education.submit_quiz(
            owner, rid, "MONEY101", paper["quiz_id"], [0] * 5, NOW + timedelta(days=i)
        )
    assert len(positions) >= 2


def test_a_paper_can_only_be_used_by_its_owner_once_and_before_it_expires(
    owner, seeded, make_resident
):
    a, b = make_resident(), make_resident()
    learn(owner, a, "MONEY101")
    learn(owner, b, "MONEY101")
    paper = education.start_quiz(owner, a, "MONEY101", NOW)
    answers = quiz_answers(owner, paper["quiz_id"], "MONEY101")
    with pytest.raises(EducationError) as e:
        education.submit_quiz(owner, b, "MONEY101", paper["quiz_id"], answers, NOW)
    assert e.value.code == "NOT_FOUND"
    with pytest.raises(EducationError) as e:
        education.submit_quiz(owner, a, "WORKMATH", paper["quiz_id"], answers, NOW)
    assert e.value.code in ("NOT_FOUND", "FEATURE_LOCKED", "PREREQ_MISSING")
    done = education.submit_quiz(owner, a, "MONEY101", paper["quiz_id"], answers, NOW)
    assert done["passed"]
    with pytest.raises(EducationError) as e:
        education.submit_quiz(owner, a, "MONEY101", paper["quiz_id"], answers, NOW)
    assert e.value.code == "ALREADY_SUBMITTED"
    stale = education.start_quiz(owner, b, "MONEY101", NOW)
    with pytest.raises(EducationError) as e:
        education.submit_quiz(
            owner, b, "MONEY101", stale["quiz_id"], answers, NOW + timedelta(hours=1)
        )
    assert e.value.code == "EXPIRED"


# ---------------- pacing: attempt limits and cooldowns ----------------
def test_coming_back_to_an_open_paper_does_not_use_another_attempt(owner, seeded, make_resident):
    rid = make_resident()
    learn(owner, rid, "MONEY101")
    first = education.start_quiz(owner, rid, "MONEY101", NOW)
    again = education.start_quiz(owner, rid, "MONEY101", NOW + timedelta(minutes=5))
    assert again["quiz_id"] == first["quiz_id"] and again["questions"] == first["questions"]
    assert owner.execute(select(func.count(QuizSession.id))).scalar() >= 1
    assert education.attempts_view(owner, rid, "MONEY101", NOW)["attempts_left"] == 4


def test_a_failed_attempt_means_a_short_wait_that_says_when_it_ends(owner, seeded, make_resident):
    rid = make_resident()
    learn(owner, rid, "MONEY101")
    take_quiz(owner, rid, "MONEY101", NOW, correct=False)
    with pytest.raises(EducationError) as e:
        education.start_quiz(owner, rid, "MONEY101", NOW + timedelta(minutes=3))
    assert e.value.code == "COOLDOWN" and e.value.retry_at == NOW + timedelta(minutes=10)
    assert (
        education.start_quiz(owner, rid, "MONEY101", NOW + timedelta(minutes=10))["attempt_no"] == 2
    )


def test_too_many_attempts_pause_the_quiz_until_the_oldest_ages_out_but_never_the_lessons(
    owner, seeded, make_resident
):
    rid = make_resident()
    learn(owner, rid, "MONEY101")
    for i in range(5):
        take_quiz(owner, rid, "MONEY101", NOW + timedelta(minutes=11 * i), correct=False)
    soon = NOW + timedelta(hours=2)
    with pytest.raises(EducationError) as e:
        education.start_quiz(owner, rid, "MONEY101", soon)
    assert e.value.code == "ATTEMPTS_EXHAUSTED" and e.value.retry_at == NOW + timedelta(hours=24)
    # the lessons stay open the whole time, and review is always possible
    assert education.get_course(owner, rid, "MONEY101", soon)["lessons"]
    assert take_quiz(owner, rid, "MONEY101", NOW + timedelta(hours=24, minutes=1))["passed"]


def test_limits_are_config_and_can_be_overridden_per_course(owner, seeded, make_resident):
    payload = json.loads(json.dumps(get_current(owner, "courses").payload))
    payload["quiz_defaults"]["max_attempts"] = 1
    for c in payload["courses"]:
        if c["code"] == "NUM101":
            c["quiz"]["max_attempts"] = 3
    set_config(owner, SYSTEM, "courses", payload, "test: tighter attempts")
    rid = make_resident()
    learn(owner, rid, "MONEY101")
    learn(owner, rid, "NUM101")
    take_quiz(owner, rid, "MONEY101", NOW, correct=False)
    with pytest.raises(EducationError) as e:
        education.start_quiz(owner, rid, "MONEY101", NOW + timedelta(minutes=20))
    assert e.value.code == "ATTEMPTS_EXHAUSTED"
    take_quiz(owner, rid, "NUM101", NOW, correct=False)
    education.start_quiz(owner, rid, "NUM101", NOW + timedelta(minutes=20))  # three are allowed


# ---------------- reading levels and languages ----------------
def test_the_easier_version_is_used_when_staff_set_it_and_others_fall_back(
    owner, seeded, make_resident
):
    easy, normal = make_resident(), make_resident()
    owner.get(Resident, easy).reading_level = "simple"
    owner.flush()
    e = education.get_course(owner, easy, "LIT101", NOW)["lessons"][0]["body"]["en"]
    n = education.get_course(owner, normal, "LIT101", NOW)["lessons"][0]["body"]["en"]
    assert e != n and len(e) < len(n)
    # a course with no easier version gives the standard text to everyone
    assert (
        education.get_course(owner, easy, "MONEY101", NOW)["lessons"][0]["body"]
        == education.get_course(owner, normal, "MONEY101", NOW)["lessons"][0]["body"]
    )


def test_a_course_without_spanish_shows_the_english_text_and_says_so(owner, seeded, make_resident):
    rid = make_resident()
    give(owner, rid, 300)
    finish(owner, rid, "NUM101")
    course = education.get_course(owner, rid, "TRADES101", NOW)
    assert course["languages"] == ["en"]
    lesson = course["lessons"][0]
    assert lesson["body"]["es"] == lesson["body"]["en"]
    spanish = education.get_course(owner, rid, "NUM101", NOW)["lessons"][0]["body"]
    assert spanish["es"] != spanish["en"]


# ---------------- points and certificates ----------------
def test_the_points_a_course_earns_come_from_config_with_a_per_course_override(
    owner, seeded, make_resident
):
    payload = json.loads(json.dumps(get_current(owner, "courses").payload))
    payload["points_by_level"]["basic"] = "program_certificate"
    for c in payload["courses"]:
        if c["code"] == "LIT101":
            c["points_kind"] = "advanced_course"
    set_config(owner, SYSTEM, "courses", payload, "test: reward reading more")
    rid = make_resident()
    assert finish(owner, rid, "MONEY101")["points_awarded"] == 200  # level mapping changed
    assert finish(owner, rid, "LIT101")["points_awarded"] == 100  # this course's own kind


def test_finishing_a_course_issues_one_certificate_with_a_printable_record(
    owner, seeded, make_resident
):
    rid = make_resident()
    owner.get(Resident, rid).display_name = "Synthetic Person"
    done = finish(owner, rid, "MONEY101")
    serial = done["certificate"]
    assert serial.startswith("MONEY101-")
    again = take_quiz(owner, rid, "MONEY101", NOW + timedelta(hours=1))
    assert again["certificate"] is None and again["already_completed"]
    certs = education.certificates_for(owner, rid)
    assert [c["serial"] for c in certs] == [serial]
    view = education.certificate(owner, rid, serial)
    assert view["resident"] == "Synthetic Person" and view["score"] == "5 of 5"
    assert view["title"]["es"] == "Fundamentos del dinero diario" and view["level"] == "basic"
    assert listing_has_serial(owner, rid, "MONEY101", serial)
    other = make_resident()
    with pytest.raises(EducationError) as e:
        education.certificate(owner, other, serial)  # nobody else can open it
    assert e.value.code == "NOT_FOUND"
    assert education.certificates_for(owner, other) == []


def listing_has_serial(owner, rid, code, serial):
    return {c["code"]: c["certificate"] for c in education.list_courses(owner, rid, NOW)}[
        code
    ] == serial


def test_certificates_cannot_be_changed_or_deleted(owner, seeded, make_resident):
    rid = make_resident()
    finish(owner, rid, "MONEY101")
    for sql in ("UPDATE certificates SET correct = 0", "DELETE FROM certificates"):
        with pytest.raises(DBAPIError):
            with owner.begin_nested():
                owner.execute(text(sql))


def test_a_failed_attempt_earns_nothing_and_is_recorded(owner, seeded, make_resident):
    rid = make_resident()
    learn(owner, rid, "MONEY101")
    res = take_quiz(owner, rid, "MONEY101", NOW, correct=False)
    assert not res["passed"] and res["certificate"] is None
    assert res["attempts"]["code"] == "COOLDOWN" and res["attempts"]["retry_at"]
    assert owner.execute(select(func.count(Certificate.id))).scalar() == 0
    assert owner.execute(
        select(QuizAttempt.passed).where(QuizAttempt.resident_id == rid)
    ).scalars().all() == [False]
    assert not owner.execute(select(PointEvent).where(PointEvent.resident_id == rid)).first()


# ---------------- adding a course, and catching bad ones ----------------
def copy_course(src: str, dst_root: Path, new_code: str) -> Path:
    dst = dst_root / new_code
    shutil.copytree(COURSES_DIR / src, dst)
    manifest = json.loads((dst / "course.json").read_text())
    manifest["code"] = new_code
    manifest["title"] = {k: f"{v} (copy)" for k, v in manifest["title"].items()}
    (dst / "course.json").write_text(json.dumps(manifest))
    return dst


def test_a_new_course_is_just_a_folder_and_needs_no_code(owner, seeded, make_resident):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for existing in COURSES_DIR.iterdir():
            shutil.copytree(existing, root / existing.name)
        copy_course("NUM101", root, "NUM102")
        config = load_config(courses_dir=root)["courses"]
    assert "NUM102" in {c["code"] for c in config["courses"]}
    set_config(owner, SYSTEM, "courses", config, "test: add a course by adding a folder")
    rid = make_resident()
    listing = {c["code"]: c for c in education.list_courses(owner, rid, NOW)}
    assert listing["NUM102"]["allowed"]
    assert finish(owner, rid, "NUM102")["passed"]


def test_malformed_courses_are_caught_with_every_problem_listed(tmp_path):
    bad = tmp_path / "BAD1"
    (bad / "lessons").mkdir(parents=True)
    (bad / "course.json").write_text(
        json.dumps(
            {
                "code": "BAD1",
                "level": "basic",
                "languages": ["en", "es"],
                "title": {"en": "Only English"},
                "pass_mark": 3,
                "prerequisites": ["NOPE"],
                "lessons": ["one"],
            }
        )
    )
    with pytest.raises(CourseFormatError) as e:
        load_course_folder(bad)
    text_ = "\n".join(e.value.problems)
    for needle in (
        "missing quiz.json",
        "pass_mark",
        "missing es text",
        "missing file lessons/one.en.md",
    ):
        assert needle in text_
    (tmp_path / "BAD2").mkdir()
    (tmp_path / "BAD2" / "course.json").write_text("{not json")
    with pytest.raises(CourseFormatError, match="not valid JSON"):
        load_courses(tmp_path)
    wrong_name = copy_course("NUM101", tmp_path, "OTHER1")
    (wrong_name / "course.json").write_text((COURSES_DIR / "NUM101" / "course.json").read_text())
    with pytest.raises(CourseFormatError, match="folder name must match"):
        load_course_folder(wrong_name)


def test_a_catalogue_that_breaks_the_rules_is_refused(tmp_path):
    for existing in COURSES_DIR.iterdir():
        shutil.copytree(existing, tmp_path / existing.name)
    manifest = json.loads((tmp_path / "LIT101" / "course.json").read_text())
    manifest["prerequisites"] = ["JOBS101"]  # a basic course may not need an advanced one
    (tmp_path / "LIT101" / "course.json").write_text(json.dumps(manifest))
    with pytest.raises(CourseFormatError) as e:
        load_config(courses_dir=tmp_path)
    assert "only require basic" in str(e.value) or "circle" in str(e.value)


def test_the_validator_command_line_reports_and_exits_non_zero(tmp_path):
    import subprocess
    import sys

    root = Path(__file__).resolve().parents[2]
    ok = subprocess.run(
        [sys.executable, str(root / "scripts/courses.py"), "validate"],
        capture_output=True,
        text=True,
        cwd=root,
    )
    assert ok.returncode == 0 and "8 courses" in ok.stdout
    broken = tmp_path / "BAD3"
    (broken / "lessons").mkdir(parents=True)
    (broken / "course.json").write_text("{}")
    bad = subprocess.run(
        [sys.executable, str(root / "scripts/courses.py"), "validate", str(broken)],
        capture_output=True,
        text=True,
        cwd=root,
    )
    assert bad.returncode == 1 and "problem" in bad.stderr
