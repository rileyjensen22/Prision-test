import statistics
from datetime import UTC, date, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from isd.engine.public_log import (
    RECORD_FIELDS,
    aggregate,
    assert_clean,
    build_record,
    outcome_of,
    pseudonym,
    suppress,
    week_start,
)
from isd.engine.welfare import WelfareRules, activity_flags, out_of_cell_flags

RULES = WelfareRules(7, 21, 7, 0.3, 0.5, 3)
N = RULES.history_needed  # 28


def types(flags):
    return [f.type for f in flags]


# ---- welfare ----
def test_steady_activity_flags_nothing():
    assert activity_flags([3] * N, [1] * N, 0, 60, RULES) == []


def test_sharp_drop_against_own_baseline():
    usage = [4] * 21 + [1] * 7  # 4/day -> 1/day = 25% of usual, under the 30% line
    contact = [1] * N
    assert types(activity_flags(usage, contact, 0, 60, RULES)) == ["usage_drop"]
    just_ok = [4] * 21 + [2] * 7  # 50%
    assert activity_flags(just_ok, contact, 0, 60, RULES) == []


def test_drop_threshold_is_relative_to_each_person():
    quiet = [1] * 21 + [0] * 7  # usual 1/day, now 0
    busy = [20] * 21 + [5] * 7  # usual 20/day, now 5 (25%)
    assert "usage_drop" in types(activity_flags(quiet, [1] * N, 0, 60, RULES))
    assert "usage_drop" in types(activity_flags(busy, [1] * N, 0, 60, RULES))
    assert activity_flags([20] * 21 + [8] * 7, [1] * N, 0, 60, RULES) == []


def test_rarely_active_residents_are_not_flagged_for_drops():
    assert activity_flags([0] * 21 + [0] * 7, [0] * N, 1, 60, RULES) == []
    barely = [1 if i % 5 == 0 else 0 for i in range(21)] + [0] * 7  # ~0.2/day usual
    assert activity_flags(barely, [1] * N, 0, 60, RULES) == []


def test_contact_drop_and_no_contact():
    contact = [2] * 21 + [0] * 7
    assert types(activity_flags([3] * N, contact, 3, 60, RULES)) == ["contact_drop"]
    fl = activity_flags([3] * N, contact, 7, 60, RULES)  # seven days of silence says it already
    assert types(fl) == ["no_contact"] and fl[0].detail == {"days": 7, "never": False}
    assert activity_flags([3] * N, [1] * N, 6, 60, RULES) == []


def test_new_residents_get_no_drop_flags_but_can_have_no_contact():
    assert activity_flags([0] * N, [0] * N, None, 5, RULES) == []  # only 5 days here
    fl = activity_flags([0] * N, [0] * N, None, 9, RULES)
    assert types(fl) == ["no_contact"] and fl[0].detail["never"] is True
    assert activity_flags([4] * 21 + [0] * 7, [1] * N, 0, 20, RULES) == []  # short history


@given(st.integers(1, 30), st.integers(0, 28))
def test_constant_activity_never_flags_a_drop(level, since):
    flags = activity_flags([level] * N, [level] * N, min(since, 6), 100, RULES)
    assert flags == []


@given(st.lists(st.integers(0, 10), min_size=N, max_size=N), st.integers(2, 5))
def test_scaling_a_residents_activity_does_not_change_a_drop_decision(series, k):
    base = statistics.fmean(series[:21])
    if base < RULES.min_baseline_per_day:
        return
    big = [x * k for x in series]
    a = "usage_drop" in types(activity_flags(series, [1] * N, 0, 100, RULES))
    b = "usage_drop" in types(activity_flags(big, [1] * N, 0, 100, RULES))
    assert a == b


def test_out_of_cell_flags():
    d0 = date(2026, 3, 2)
    days = [(d0 + timedelta(days=i), m) for i, m in enumerate([90, 45, 60, 120, None, None, None])]
    fl = out_of_cell_flags(days, 60, 3)
    assert types(fl) == ["out_of_cell_below", "out_of_cell_unrecorded"]
    assert fl[0].detail["days"] == ["2026-03-03"] and fl[0].detail["lowest"] == 45
    assert fl[1].detail == {"days": 3}
    assert (
        out_of_cell_flags([(d0, 60), (d0 + timedelta(days=1), 61)], 60, 3) == []
    )  # exactly the minimum is fine
    assert (
        out_of_cell_flags([(d0, None), (d0 + timedelta(days=1), None)], 60, 3) == []
    )  # only 2 unrecorded


# ---- public log ----
SALT = "test-salt"
NOW = datetime(2026, 3, 20, 12, tzinfo=UTC)


def rec(**over):
    base = dict(
        sanction_id=7,
        resident_code="RES-0001",
        issued_at=datetime(2026, 3, 4, 15, 30, tzinfo=UTC),
        code="DISRUPT",
        severity="minor",
        duration_hours=24,
        hours_served=24.0,
        issued_by_role="officer",
        confirmed_by_role=None,
        status="active",
        ends_at=NOW - timedelta(days=1),
        appeal="none",
        now=NOW,
        salt=SALT,
    )
    return build_record(**{**base, **over})


def test_record_has_only_public_fields_and_no_identity():
    r = rec()
    assert set(r) == set(RECORD_FIELDS)
    assert (
        "RES-0001" not in str(r) and r["resident"].startswith("R-") and r["event"].startswith("E-")
    )
    assert r["week"] == "2026-03-02" and r["outcome"] == "ended"  # Monday of that week, not 4 March


def test_pseudonyms_are_stable_salted_and_distinct():
    assert pseudonym("R", "RES-1", SALT) == pseudonym("R", "RES-1", SALT)
    assert pseudonym("R", "RES-1", SALT) != pseudonym("R", "RES-2", SALT)
    assert pseudonym("R", "RES-1", SALT) != pseudonym("R", "RES-1", "other-salt")
    assert pseudonym("R", "1", SALT) != pseudonym("E", "1", SALT)


def test_clean_check_rejects_extra_fields_and_unknown_values():
    good = rec()
    with pytest.raises(ValueError):
        assert_clean({**good, "staff": "officer1"})
    with pytest.raises(ValueError):
        assert_clean({**good, "outcome": "who knows"})


def test_outcomes():
    assert outcome_of("active", NOW + timedelta(hours=1), NOW) == "active"
    assert outcome_of("active", NOW, NOW) == "ended"
    assert outcome_of("overturned", None, NOW) == "overturned"


@given(st.integers(0, 40), st.integers(2, 6))
def test_small_counts_are_suppressed(n, k):
    s = suppress(n, k)
    assert (s == f"<{k}") == (0 < n < k)
    assert s == n or isinstance(s, str)


def test_aggregate_per_role_with_suppression():
    rs = [rec(sanction_id=i) for i in range(5)] + [
        rec(sanction_id=9, issued_by_role="supervisor", status="rejected", ends_at=None)
    ]
    agg = aggregate(rs, 3)
    assert agg["by_issuing_role"]["officer"]["issued"] == 5
    assert agg["by_issuing_role"]["supervisor"]["issued"] == "<3"
    assert agg["by_code"] == {"DISRUPT": 6}
    assert week_start(date(2026, 3, 8)) == "2026-03-02"  # a Sunday belongs to the week before
