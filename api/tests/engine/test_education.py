import random
from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from isd.engine.education import attempt_decision, draw_quiz, grade_drawn

NOW = datetime(2026, 3, 2, 9, 0, tzinfo=UTC)
BANK = [{"id": f"q{i}", "choices": [{"en": c} for c in "abcd"], "answer": i % 4} for i in range(8)]
BY_ID = {q["id"]: q for q in BANK}


def correct_for(drawn):
    """The displayed choice number that is right for each drawn question."""
    return [d.order.index(BY_ID[d.id]["answer"]) for d in drawn]


def test_a_draw_takes_distinct_questions_and_every_choice_once():
    drawn = draw_quiz(BANK, 5, random.Random(1))
    assert len({d.id for d in drawn}) == 5
    assert all(sorted(d.order) == [0, 1, 2, 3] for d in drawn)


@given(st.integers(0, 10_000), st.integers(1, 8))
def test_answering_every_question_correctly_always_passes_whatever_the_shuffle(seed, n):
    drawn = draw_quiz(BANK, n, random.Random(seed))
    result = grade_drawn(BY_ID, drawn, correct_for(drawn), 0.6)
    assert result.correct == n and result.passed


@given(st.integers(0, 10_000))
def test_the_same_displayed_numbers_are_wrong_when_the_choices_move(seed):
    drawn = draw_quiz(BANK, 4, random.Random(seed))
    right = correct_for(drawn)
    wrong = [(r + 1) % 4 for r in right]
    assert grade_drawn(BY_ID, drawn, wrong, 0.6).correct == 0


def test_different_seeds_give_different_questions_and_orders():
    seen = {
        tuple((d.id, tuple(d.order)) for d in draw_quiz(BANK, 4, random.Random(s)))
        for s in range(30)
    }
    assert len(seen) > 10


def test_a_full_bank_draw_is_still_shuffled():
    orders = {tuple(d.id for d in draw_quiz(BANK[:5], 5, random.Random(s))) for s in range(30)}
    assert len(orders) > 5


def test_grading_refuses_a_short_or_out_of_range_answer_sheet():
    drawn = draw_quiz(BANK, 3, random.Random(2))
    for bad in ([0, 0], [0, 0, 0, 0], [0, 0, 9], [0, 0, -1]):
        with pytest.raises(ValueError):
            grade_drawn(BY_ID, drawn, bad, 0.6)


def test_pass_mark_is_inclusive():
    drawn = draw_quiz(BANK, 5, random.Random(3))
    right = correct_for(drawn)
    three_of_five = [right[0], right[1], right[2], (right[3] + 1) % 4, (right[4] + 1) % 4]
    assert grade_drawn(BY_ID, drawn, three_of_five, 0.6).passed
    two_of_five = [right[0], right[1], (right[2] + 1) % 4, (right[3] + 1) % 4, (right[4] + 1) % 4]
    assert not grade_drawn(BY_ID, drawn, two_of_five, 0.6).passed


def decide(starts, last_failed=None, now=NOW, **kw):
    kw = {"max_attempts": 3, "window_hours": 24, "cooldown_minutes": 10, **kw}
    return attempt_decision(starts, last_failed, now, **kw)


def test_the_first_attempt_is_always_allowed():
    d = decide([])
    assert d.allowed and d.attempts_left == 3 and d.retry_at is None


def test_a_failed_attempt_makes_you_wait_a_little_then_you_may_try_again():
    failed = NOW - timedelta(minutes=4)
    d = decide([NOW - timedelta(minutes=5)], failed)
    assert not d.allowed and d.code == "COOLDOWN" and d.retry_at == failed + timedelta(minutes=10)
    assert decide([NOW - timedelta(minutes=30)], NOW - timedelta(minutes=29)).allowed


def test_too_many_attempts_in_the_window_wait_until_the_oldest_ages_out():
    starts = [NOW - timedelta(hours=h) for h in (20, 10, 1)]
    d = decide(starts, NOW - timedelta(hours=1))
    assert not d.allowed and d.code == "ATTEMPTS_EXHAUSTED"
    assert d.retry_at == starts[0] + timedelta(hours=24) and d.attempts_left == 0
    assert decide(starts, NOW - timedelta(hours=1), now=NOW + timedelta(hours=5)).allowed
