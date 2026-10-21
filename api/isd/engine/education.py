"""Quiz grading and the points an education completion earns."""

from dataclasses import dataclass

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
