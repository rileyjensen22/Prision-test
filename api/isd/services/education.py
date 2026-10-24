"""Education: lessons, resume, a randomised quiz with paced attempts, points and certificates.

Course content comes from the versioned `courses` config (built from folders under
content/courses). Eligibility comes from get_entitlements for the course's level plus its
prerequisites. Quiz limits only pace attempts; they never close the lessons.
"""

import random
import secrets
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from isd.engine.education import (
    LEVEL_TO_FEATURE,
    DrawnQuestion,
    attempt_decision,
    draw_quiz,
    grade_drawn,
)
from isd.models import Certificate, CourseProgress, QuizAttempt, QuizSession, Resident
from isd.services.audit import SYSTEM
from isd.services.config_store import get_current
from isd.services.entitlement_service import get_entitlements
from isd.services.points import add_point_event


class EducationError(ValueError):
    def __init__(self, code: str, message: str, retry_at: datetime | None = None, **extra: Any):
        super().__init__(message)
        self.code = code
        self.retry_at = retry_at
        self.extra = extra


def _config(session: Session) -> dict:
    return get_current(session, "courses").payload


def _courses(session: Session) -> dict[str, dict[str, Any]]:
    return {c["code"]: c for c in _config(session)["courses"]}


def _course(session: Session, code: str) -> dict[str, Any]:
    course = _courses(session).get(code)
    if course is None:
        raise EducationError("NOT_FOUND", "course not found")
    return course


def quiz_settings(session: Session, course: dict) -> dict:
    return {**_config(session)["quiz_defaults"], **course["quiz"]}


def points_kind(session: Session, course: dict) -> str:
    return course.get("points_kind") or _config(session)["points_by_level"][course["level"]]


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


def _progress_readonly(session: Session, resident_id: int, code: str):
    return session.execute(
        select(CourseProgress).where(
            CourseProgress.resident_id == resident_id, CourseProgress.course_code == code
        )
    ).scalar()


def _completed_codes(session: Session, resident_id: int) -> set[str]:
    return set(
        session.execute(
            select(CourseProgress.course_code).where(
                CourseProgress.resident_id == resident_id, CourseProgress.completed_at.is_not(None)
            )
        ).scalars()
    )


def prerequisites_missing(session: Session, resident_id: int, course: dict) -> list[str]:
    done = _completed_codes(session, resident_id)
    return [p for p in course["prerequisites"] if p not in done]


def _gate(session: Session, resident_id: int, course: dict, now: datetime):
    ent = get_entitlements(session, resident_id, now)
    return ent, ent.features[LEVEL_TO_FEATURE[course["level"]]]


def _check_open(session: Session, resident_id: int, course: dict, now: datetime):
    ent, fe = _gate(session, resident_id, course, now)
    if not fe.allowed:
        raise EducationError("FEATURE_LOCKED", "course is locked")
    missing = prerequisites_missing(session, resident_id, course)
    if missing:
        raise EducationError("PREREQ_MISSING", "finish the earlier courses first", missing=missing)
    return ent


def _titles(session: Session, codes: list[str]) -> dict[str, dict]:
    courses = _courses(session)
    return {c: courses[c]["title"] for c in codes if c in courses}


def list_courses(session: Session, resident_id: int, now: datetime) -> list[dict]:
    out = []
    ent = get_entitlements(session, resident_id, now)  # once, not once per course
    done = _completed_codes(session, resident_id)
    progress = {
        p.course_code: p
        for p in session.execute(
            select(CourseProgress).where(CourseProgress.resident_id == resident_id)
        ).scalars()
    }
    certs = {
        c.course_code: c.serial
        for c in session.execute(
            select(Certificate).where(Certificate.resident_id == resident_id)
        ).scalars()
    }
    for c in _courses(session).values():
        fe = ent.features[LEVEL_TO_FEATURE[c["level"]]]
        p = progress.get(c["code"])
        missing = [q for q in c["prerequisites"] if q not in done]
        reasons = [
            {"code": r.code, "params": r.params, "ends_at": r.ends_at, "source": r.source}
            for r in fe.reasons
        ]
        if fe.allowed and missing:  # a prerequisite is a plain "finish these first", not a lock
            reasons = [{"code": "PREREQUISITE", "params": {}, "ends_at": None, "source": "course"}]
        out.append(
            {
                "code": c["code"],
                "level": c["level"],
                "title": c["title"],
                "summary": c.get("summary"),
                "languages": c["languages"],
                "lessons": len(c["lessons"]),
                "lessons_done": len(p.lessons_done) if p else 0,
                "completed": bool(p and p.completed_at),
                "allowed": fe.allowed and not missing,
                "prerequisites": c["prerequisites"],
                "missing": missing,
                "missing_titles": _titles(session, missing),
                "certificate": certs.get(c["code"]),
                "reasons": reasons,
            }
        )
    return out


def _lesson_text(lesson: dict, level: str, languages: list[str]) -> dict[str, str]:
    """Bilingual {en, es} Markdown for a resident's reading level. A language the course does not
    have falls back to English; a missing easier version falls back to the standard one."""
    bodies = lesson["body"].get(level) or lesson["body"]["standard"]
    standard = lesson["body"]["standard"]
    return {lang: bodies.get(lang) or standard.get(lang) or standard["en"] for lang in ("en", "es")}


def get_course(session: Session, resident_id: int, code: str, now: datetime) -> dict:
    """Lessons (never quiz answers; the quiz is drawn separately)."""
    course = _course(session, code)
    _check_open(session, resident_id, course, now)
    resident = session.get(Resident, resident_id)
    level = (
        resident.reading_level if resident.reading_level in ("simple", "standard") else "standard"
    )
    p = _progress_readonly(session, resident_id, code)
    settings = quiz_settings(session, course)
    return {
        "code": code,
        "level": course["level"],
        "title": course["title"],
        "languages": course["languages"],
        "lessons": [
            {
                "id": le["id"],
                "title": {
                    lang: le["title"].get(lang) or le["title"]["en"] for lang in ("en", "es")
                },
                "body": _lesson_text(le, level, course["languages"]),
            }
            for le in course["lessons"]
        ],
        "quiz": {
            "questions": min(settings["draw"], len(course["quiz"]["bank"])),
            "pass_mark": course["pass_mark"],
        },
        "lessons_done": list(p.lessons_done) if p else [],
        "last_lesson": p.last_lesson if p else None,
        "completed": bool(p and p.completed_at),
    }


def complete_lesson(
    session: Session, resident_id: int, code: str, lesson_id: str, now: datetime
) -> dict:
    """Idempotent, so a lesson finished offline can be replayed any number of times."""
    course = _course(session, code)
    if lesson_id not in {le["id"] for le in course["lessons"]}:
        raise EducationError("NOT_FOUND", "lesson not found")
    _check_open(session, resident_id, course, now)
    p = _progress(session, resident_id, code, create=True)
    if lesson_id not in p.lessons_done:
        p.lessons_done = [*p.lessons_done, lesson_id]
    p.last_lesson, p.updated_at = lesson_id, now
    return {"lessons_done": list(p.lessons_done), "total": len(course["lessons"])}


# ---------------- the quiz ----------------
def _history(session: Session, resident_id: int, code: str):
    starts = list(
        session.execute(
            select(QuizSession.issued_at).where(
                QuizSession.resident_id == resident_id, QuizSession.course_code == code
            )
        ).scalars()
    )
    last_failed = session.execute(
        select(QuizSession.submitted_at)
        .where(
            QuizSession.resident_id == resident_id,
            QuizSession.course_code == code,
            QuizSession.passed.is_(False),
        )
        .order_by(QuizSession.submitted_at.desc())
        .limit(1)
    ).scalar()
    return starts, last_failed


def attempts_view(session: Session, resident_id: int, code: str, now: datetime) -> dict:
    course = _course(session, code)
    s = quiz_settings(session, course)
    starts, failed = _history(session, resident_id, code)
    d = attempt_decision(
        starts,
        failed,
        now,
        max_attempts=s["max_attempts"],
        window_hours=s["window_hours"],
        cooldown_minutes=s["cooldown_minutes"],
    )
    return {
        "allowed": d.allowed,
        "code": d.code,
        "retry_at": d.retry_at.isoformat() if d.retry_at else None,
        "attempts_left": d.attempts_left,
    }


def _shown(course: dict, drawn: list[DrawnQuestion]) -> list[dict]:
    bank = {q["id"]: q for q in course["quiz"]["bank"]}
    return [
        {
            "id": d.id,
            "prompt": _bi(bank[d.id]["prompt"]),
            "choices": [_bi(bank[d.id]["choices"][i]) for i in d.order],
        }
        for d in drawn
    ]


def _bi(text: dict) -> dict:
    return {"en": text["en"], "es": text.get("es") or text["en"]}


def start_quiz(
    session: Session,
    resident_id: int,
    code: str,
    now: datetime,
    rng: random.Random | None = None,
) -> dict:
    """A fresh paper (random questions, shuffled choices), or the open one if there is one.
    Starting a paper counts as an attempt; resuming it does not."""
    course = _course(session, code)
    _check_open(session, resident_id, course, now)
    p = _progress(session, resident_id, code, create=True)
    if len(p.lessons_done) < len(course["lessons"]):
        raise EducationError("LESSONS_INCOMPLETE", "finish all lessons first")
    open_paper = session.execute(
        select(QuizSession)
        .where(
            QuizSession.resident_id == resident_id,
            QuizSession.course_code == code,
            QuizSession.status == "open",
        )
        .with_for_update()
    ).scalar()
    if open_paper is not None:
        if open_paper.expires_at > now:
            drawn = [DrawnQuestion(q["id"], q["order"]) for q in open_paper.questions]
            return _paper(open_paper, course, drawn, session, resident_id, now)
        open_paper.status = "expired"
    attempts = attempts_view(session, resident_id, code, now)
    if not attempts["allowed"]:
        raise EducationError(
            attempts["code"],
            "wait before the next attempt"
            if attempts["code"] == "COOLDOWN"
            else "no more attempts for now",
            retry_at=datetime.fromisoformat(attempts["retry_at"]),
        )
    settings = quiz_settings(session, course)
    bank = course["quiz"]["bank"]
    drawn = draw_quiz(bank, min(settings["draw"], len(bank)), rng or random.SystemRandom())
    starts, _ = _history(session, resident_id, code)
    paper = QuizSession(
        resident_id=resident_id,
        course_code=code,
        questions=[{"id": d.id, "order": d.order} for d in drawn],
        attempt_no=len(starts) + 1,
        issued_at=now,
        expires_at=now + timedelta(minutes=settings["quiz_minutes"]),
    )
    session.add(paper)
    session.flush()
    return _paper(paper, course, drawn, session, resident_id, now)


def _paper(paper, course, drawn, session, resident_id, now) -> dict:
    return {
        "quiz_id": paper.id,
        "questions": _shown(course, drawn),
        "expires_at": paper.expires_at.isoformat(),
        "attempt_no": paper.attempt_no,
        "attempts_left": attempts_view(session, resident_id, course["code"], now)["attempts_left"],
    }


def submit_quiz(
    session: Session, resident_id: int, code: str, quiz_id: int, answers: list[int], now: datetime
) -> dict:
    course = _course(session, code)
    ent_before = _check_open(session, resident_id, course, now)
    paper = session.execute(
        select(QuizSession).where(QuizSession.id == quiz_id).with_for_update()
    ).scalar()
    if paper is None or paper.resident_id != resident_id or paper.course_code != code:
        raise EducationError("NOT_FOUND", "quiz not found")
    if paper.status != "open":
        raise EducationError("ALREADY_SUBMITTED", "this quiz was already handed in")
    if paper.expires_at <= now:
        paper.status = "expired"
        raise EducationError("EXPIRED", "this quiz timed out; start a new one")
    drawn = [DrawnQuestion(q["id"], q["order"]) for q in paper.questions]
    bank = {q["id"]: q for q in course["quiz"]["bank"]}
    try:
        result = grade_drawn(bank, drawn, answers, course["pass_mark"])
    except ValueError as e:
        raise EducationError("BAD_ANSWERS", str(e)) from e
    paper.status, paper.submitted_at, paper.passed = "submitted", now, result.passed
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
    p = _progress(session, resident_id, code, create=True)
    awarded, serial = 0, None
    already = p.completed_at is not None
    if result.passed and not already:
        p.completed_at = now
        ev = add_point_event(session, SYSTEM, resident_id, points_kind(session, course), now)
        awarded = ev.points
        serial = _issue_certificate(session, resident_id, course, result.correct, result.total, now)
    ent_after = get_entitlements(session, resident_id, now)
    out = {
        "correct": result.correct,
        "total": result.total,
        "passed": result.passed,
        "points_awarded": awarded,
        "already_completed": already and result.passed,
        "certificate": serial,
        "tier_before": ent_before.effective_tier,
        "tier_after": ent_after.effective_tier,
        "calls_minutes_before": ent_before.features["calls"].limits.get("minutes_per_day"),
        "calls_minutes_after": ent_after.features["calls"].limits.get("minutes_per_day"),
    }
    if not result.passed:
        out["attempts"] = attempts_view(session, resident_id, code, now)
    return out


# ---------------- certificates ----------------
def _issue_certificate(
    session: Session, resident_id: int, course: dict, correct: int, total: int, now: datetime
) -> str:
    serial = f"{course['code']}-{secrets.token_hex(4).upper()}"
    session.add(
        Certificate(
            serial=serial,
            resident_id=resident_id,
            course_code=course["code"],
            title=course["title"],
            level=course["level"],
            correct=correct,
            total=total,
            issued_at=now,
        )
    )
    session.flush()
    return serial


def certificate_view(session: Session, cert: Certificate) -> dict:
    resident = session.get(Resident, cert.resident_id)
    return {
        "serial": cert.serial,
        "course": cert.course_code,
        "title": {"en": cert.title["en"], "es": cert.title.get("es") or cert.title["en"]},
        "level": cert.level,
        "score": f"{cert.correct} of {cert.total}",
        "issued_at": cert.issued_at.isoformat(),
        "resident": resident.display_name,
        "resident_code": resident.code,
    }


def certificates_for(session: Session, resident_id: int) -> list[dict]:
    rows = session.execute(
        select(Certificate)
        .where(Certificate.resident_id == resident_id)
        .order_by(Certificate.issued_at, Certificate.id)
    ).scalars()
    return [certificate_view(session, c) for c in rows]


def certificate(session: Session, resident_id: int, serial: str) -> dict:
    cert = session.execute(
        select(Certificate).where(
            Certificate.serial == serial, Certificate.resident_id == resident_id
        )
    ).scalar()
    if cert is None:
        raise EducationError("NOT_FOUND", "certificate not found")
    return certificate_view(session, cert)
