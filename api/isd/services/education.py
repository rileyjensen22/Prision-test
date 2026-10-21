"""Education: lessons, quiz, completion points. Content comes from versioned config."""

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from isd.engine.education import LEVEL_TO_FEATURE, LEVEL_TO_POINTS_KIND, grade_quiz
from isd.models import CourseProgress, QuizAttempt
from isd.services.audit import SYSTEM
from isd.services.config_store import get_current
from isd.services.entitlement_service import get_entitlements
from isd.services.points import add_point_event


class EducationError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _courses(session: Session) -> dict[str, dict[str, Any]]:
    return {c["code"]: c for c in get_current(session, "courses").payload["courses"]}


def _course(session: Session, code: str) -> dict[str, Any]:
    course = _courses(session).get(code)
    if course is None:
        raise EducationError("NOT_FOUND", "course not found")
    return course


def _progress(session: Session, resident_id: int, code: str, create: bool = False):
    row = session.execute(
        select(CourseProgress)
        .where(CourseProgress.resident_id == resident_id, CourseProgress.course_code == code)
        .with_for_update()
    ).scalar()
    if row is None and create:
        row = CourseProgress(resident_id=resident_id, course_code=code, lessons_done=[])
        session.add(row)
        session.flush()
    return row


def _gate(session: Session, resident_id: int, course: dict, now: datetime):
    ent = get_entitlements(session, resident_id, now)
    fe = ent.features[LEVEL_TO_FEATURE[course["level"]]]
    return ent, fe


def list_courses(session: Session, resident_id: int, now: datetime) -> list[dict]:
    out = []
    for c in _courses(session).values():
        _, fe = _gate(session, resident_id, c, now)
        p = _progress_readonly(session, resident_id, c["code"])
        out.append(
            {
                "code": c["code"],
                "level": c["level"],
                "title": c["title"],
                "lessons": len(c["lessons"]),
                "lessons_done": len(p.lessons_done) if p else 0,
                "completed": bool(p and p.completed_at),
                "allowed": fe.allowed,
                "reasons": [
                    {"code": r.code, "params": r.params, "ends_at": r.ends_at, "source": r.source}
                    for r in fe.reasons
                ],
            }
        )
    return out


def _progress_readonly(session: Session, resident_id: int, code: str):
    return session.execute(
        select(CourseProgress).where(
            CourseProgress.resident_id == resident_id, CourseProgress.course_code == code
        )
    ).scalar()


def get_course(session: Session, resident_id: int, code: str, now: datetime) -> dict:
    """Lessons and quiz questions (never the answers)."""
    course = _course(session, code)
    _, fe = _gate(session, resident_id, course, now)
    if not fe.allowed:
        raise EducationError("FEATURE_LOCKED", "course is locked")
    p = _progress_readonly(session, resident_id, code)
    return {
        "code": code,
        "level": course["level"],
        "title": course["title"],
        "lessons": [
            {"id": le["id"], "title": le["title"], "body": le["body"]} for le in course["lessons"]
        ],
        "quiz": [
            {"id": q["id"], "prompt": q["prompt"], "choices": q["choices"]} for q in course["quiz"]
        ],
        "lessons_done": list(p.lessons_done) if p else [],
        "completed": bool(p and p.completed_at),
    }


def complete_lesson(
    session: Session, resident_id: int, code: str, lesson_id: str, now: datetime
) -> dict:
    course = _course(session, code)
    if lesson_id not in {le["id"] for le in course["lessons"]}:
        raise EducationError("NOT_FOUND", "lesson not found")
    _, fe = _gate(session, resident_id, course, now)
    if not fe.allowed:
        raise EducationError("FEATURE_LOCKED", "course is locked")
    p = _progress(session, resident_id, code, create=True)
    if lesson_id not in p.lessons_done:
        p.lessons_done = [*p.lessons_done, lesson_id]
    return {"lessons_done": list(p.lessons_done), "total": len(course["lessons"])}


def submit_quiz(
    session: Session, resident_id: int, code: str, answers: list[int], now: datetime
) -> dict:
    course = _course(session, code)
    ent_before, fe = _gate(session, resident_id, course, now)
    if not fe.allowed:
        raise EducationError("FEATURE_LOCKED", "course is locked")
    p = _progress(session, resident_id, code, create=True)
    if len(p.lessons_done) < len(course["lessons"]):
        raise EducationError("LESSONS_INCOMPLETE", "finish all lessons first")
    try:
        result = grade_quiz(course["quiz"], answers, course["pass_mark"])
    except ValueError as e:
        raise EducationError("BAD_ANSWERS", str(e)) from e
    session.add(
        QuizAttempt(
            resident_id=resident_id,
            course_code=code,
            correct=result.correct,
            total=result.total,
            passed=result.passed,
            at=now,
        )
    )
    awarded = 0
    already = p.completed_at is not None
    if result.passed and not already:
        p.completed_at = now
        kind = LEVEL_TO_POINTS_KIND[course["level"]]
        ev = add_point_event(session, SYSTEM, resident_id, kind, now)
        awarded = ev.points
    ent_after = get_entitlements(session, resident_id, now)
    return {
        "correct": result.correct,
        "total": result.total,
        "passed": result.passed,
        "points_awarded": awarded,
        "already_completed": already and result.passed,
        "tier_before": ent_before.effective_tier,
        "tier_after": ent_after.effective_tier,
        "calls_minutes_before": ent_before.features["calls"].limits.get("minutes_per_day"),
        "calls_minutes_after": ent_after.features["calls"].limits.get("minutes_per_day"),
    }
