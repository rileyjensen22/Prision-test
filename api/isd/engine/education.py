"""Quiz drawing and grading, and the pacing rules for attempts. Pure."""

import random
from dataclasses import dataclass
from datetime import datetime, timedelta

LEVEL_TO_POINTS_KIND = {
    "basic": "basic_course",
    "advanced": "advanced_course",
    "program": "program_certificate",
}
# Which entitlement feature gates a course level (basic is protected baseline).
LEVEL_TO_FEATURE = {
    "basic": "basic_education",
    "advanced": "advanced_education",
    "program": "advanced_education",
}


@dataclass(frozen=True)
class QuizResult:
    correct: int
    total: int
    score: float
    passed: bool


def grade_quiz(questions: list[dict], answers: list[int], pass_mark: float) -> QuizResult:
    if len(answers) != len(questions):
        raise ValueError("answer every question")
    correct = 0
    for q, a in zip(questions, answers, strict=True):
        if not 0 <= a < len(q["choices"]):
            raise ValueError("answer out of range")
        correct += a == q["answer"]
    score = correct / len(questions)
    return QuizResult(correct, len(questions), score, score >= pass_mark)


@dataclass(frozen=True)
class DrawnQuestion:
    id: str
    order: list[int]  # the bank's choice numbers, in the order they are shown


def draw_quiz(bank: list[dict], count: int, rng: random.Random) -> list[DrawnQuestion]:
    """`count` distinct questions in a random order, each with its choices shuffled. A resident
    cannot learn answers by position, and a retry is a different paper."""
    chosen = rng.sample(bank, count)
    out = []
    for q in chosen:
        order = list(range(len(q["choices"])))
        rng.shuffle(order)
        out.append(DrawnQuestion(q["id"], order))
    return out


def grade_drawn(
    bank_by_id: dict[str, dict], drawn: list[DrawnQuestion], answers: list[int], pass_mark: float
) -> QuizResult:
    """`answers` are the numbers of the choices as they were shown."""
    if len(answers) != len(drawn):
        raise ValueError("answer every question")
    correct = 0
    for d, a in zip(drawn, answers, strict=True):
        if not isinstance(a, int) or not 0 <= a < len(d.order):
            raise ValueError("answer out of range")
        correct += d.order[a] == bank_by_id[d.id]["answer"]
    score = correct / len(drawn)
    return QuizResult(correct, len(drawn), score, score >= pass_mark)


@dataclass(frozen=True)
class AttemptDecision:
    allowed: bool
    code: str | None  # COOLDOWN | ATTEMPTS_EXHAUSTED
    retry_at: datetime | None
    attempts_left: int


def attempt_decision(
    starts: list[datetime],
    last_failed_at: datetime | None,
    now: datetime,
    *,
    max_attempts: int,
    window_hours: int,
    cooldown_minutes: int,
) -> AttemptDecision:
    """May a quiz be started now? `starts` are when earlier attempts began. Limits are pacing
    only: they never close the lessons, and every one ends at a stated time."""
    window = timedelta(hours=window_hours)
    recent = sorted(t for t in starts if now - window < t <= now)
    left = max(0, max_attempts - len(recent))
    if left == 0:
        return AttemptDecision(False, "ATTEMPTS_EXHAUSTED", recent[0] + window, 0)
    if last_failed_at is not None:
        ready = last_failed_at + timedelta(minutes=cooldown_minutes)
        if now < ready:
            return AttemptDecision(False, "COOLDOWN", ready, left)
    return AttemptDecision(True, None, None, left)
