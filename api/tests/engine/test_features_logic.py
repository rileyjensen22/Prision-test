from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from isd.engine.calls import (
    PRIVILEGED_MAX_SECONDS,
    CallDenied,
    effective_seconds,
    minutes_used,
    plan_call,
)
from isd.engine.commissary import OrderError, check_order, item_block_reason, price_order
from isd.engine.education import grade_quiz
from isd.engine.periods import period_start

T = datetime(2026, 3, 4, 15, 30, 12, 5, tzinfo=UTC)  # a Wednesday


def test_period_starts():
    assert period_start(T, "day") == datetime(2026, 3, 4, tzinfo=UTC)
    assert period_start(T, "week") == datetime(2026, 3, 2, tzinfo=UTC)  # Monday
    with pytest.raises(ValueError):
        period_start(T, "year")


@given(
    st.datetimes(
        min_value=datetime(2020, 1, 1), max_value=datetime(2035, 1, 1), timezones=st.just(UTC)
    )
)
def test_period_start_is_at_or_before_now_and_within_period(now):
    d, w = period_start(now, "day"), period_start(now, "week")
    assert w <= d <= now and now - d < timedelta(days=1)
    assert now - w < timedelta(days=7) and w.weekday() == 0


# ---- calls ----
def test_attorney_calls_are_always_allowed_unmetered_and_unmonitored():
    plan = plan_call(privileged=True, allowed=False, limit_minutes=None, used_seconds=10**6)
    assert plan.privileged and not plan.monitored and plan.max_seconds == PRIVILEGED_MAX_SECONDS


def test_regular_call_rules():
    plan = plan_call(privileged=False, allowed=True, limit_minutes=15, used_seconds=300)
    assert plan.max_seconds == 600 and plan.monitored and not plan.privileged
    with pytest.raises(CallDenied) as e:
        plan_call(privileged=False, allowed=False, limit_minutes=15, used_seconds=0)
    assert e.value.code == "FEATURE_LOCKED"
    with pytest.raises(CallDenied) as e:
        plan_call(privileged=False, allowed=True, limit_minutes=15, used_seconds=900)
    assert e.value.code == "LIMIT_REACHED"


@given(st.integers(1, 120), st.lists(st.integers(0, 7200), max_size=12))
def test_daily_minutes_never_exceeded_when_each_call_respects_its_plan(limit, attempted):
    used = 0
    for want in attempted:
        try:
            plan = plan_call(privileged=False, allowed=True, limit_minutes=limit, used_seconds=used)
        except CallDenied:
            continue
        start = T
        used += effective_seconds(start, start + timedelta(seconds=want), plan.max_seconds)
        assert used <= limit * 60


@given(st.integers(-5000, 5000), st.integers(1, 4000))
def test_effective_seconds_clamped(delta, cap):
    s = effective_seconds(T, T + timedelta(seconds=delta), cap)
    assert 0 <= s <= cap


def test_minutes_round_up():
    assert [minutes_used(s) for s in (0, 1, 60, 61)] == [0, 1, 1, 2]


# ---- commissary ----
CATALOG = {
    "A": {"price_cents": 125, "min_tier": 1, "blocked_offense_categories": []},
    "B": {"price_cents": 1200, "min_tier": 4, "blocked_offense_categories": ["X"]},
}


def test_item_restrictions_by_tier_and_offense():
    assert item_block_reason(CATALOG["B"], 3, ()) == "ITEM_TIER"
    assert item_block_reason(CATALOG["B"], 4, ("X",)) == "ITEM_OFFENSE"
    assert item_block_reason(CATALOG["B"], 4, ("Y",)) is None
    assert item_block_reason(CATALOG["A"], 1, ("X",)) is None


@given(st.dictionaries(st.sampled_from(["A", "B"]), st.integers(1, 20), min_size=1))
def test_price_is_sum_of_lines(lines):
    assert price_order(lines, CATALOG) == sum(
        CATALOG[c]["price_cents"] * q for c, q in lines.items()
    )


@pytest.mark.parametrize("lines", [{}, {"Z": 1}, {"A": 0}, {"A": 21}])
def test_bad_orders_rejected(lines):
    with pytest.raises(OrderError):
        price_order(lines, CATALOG)


@given(st.integers(1, 10**5), st.integers(0, 10**5), st.integers(0, 10**5), st.integers(0, 10**5))
def test_check_order_never_allows_overspend_or_over_limit(total, balance, limit, spent):
    try:
        check_order(total, balance, limit, spent)
    except OrderError as e:
        assert e.code in ("INSUFFICIENT_FUNDS", "WEEKLY_LIMIT")
    else:
        assert total <= balance and spent + total <= limit


# ---- education ----
QUIZ = [{"choices": ["a", "b", "c"], "answer": 1}, {"choices": ["a", "b"], "answer": 0}]


def test_grading():
    assert grade_quiz(QUIZ, [1, 0], 1.0).passed
    r = grade_quiz(QUIZ, [1, 1], 0.5)
    assert (r.correct, r.total, r.passed) == (1, 2, True)
    assert not grade_quiz(QUIZ, [0, 1], 0.5).passed


def test_grading_rejects_malformed_answers():
    for bad in ([1], [1, 0, 0], [1, 5], [-1, 0]):
        with pytest.raises(ValueError):
            grade_quiz(QUIZ, bad, 0.5)
