from datetime import UTC, datetime, timedelta

from hypothesis import given
from hypothesis import strategies as st

from isd.engine.movement import (
    attendance,
    close_intervals,
    minutes_by_day,
    overlap_minutes,
    pair_events,
)

D = datetime(2026, 3, 2, tzinfo=UTC)


def at(h, m=0, day=0):
    return D + timedelta(days=day, hours=h, minutes=m)


def test_events_pair_into_intervals_and_an_open_one_runs_to_now():
    events = [("out", at(9)), ("in", at(10)), ("out", at(13)), ("in", at(13, 30)), ("out", at(18))]
    closed, open_since = pair_events(events)
    assert closed == [(at(9), at(10)), (at(13), at(13, 30))]
    assert open_since == at(18)
    assert close_intervals(events, at(18, 45)) == [*closed, (at(18), at(18, 45))]


def test_a_stray_in_or_double_out_is_ignored_rather_than_inventing_time():
    closed, open_since = pair_events(
        [("in", at(8)), ("out", at(9)), ("out", at(9, 5)), ("in", at(10))]
    )
    assert closed == [(at(9), at(10))] and open_since is None


def test_minutes_are_split_across_midnight():
    got = minutes_by_day([(at(23), at(1, 30, day=1))])
    assert got == {D.date(): 60, (D + timedelta(days=1)).date(): 90}


@given(
    st.lists(st.tuples(st.integers(0, 3000), st.integers(1, 700)), max_size=8),
)
def test_the_daily_minutes_always_add_up_to_the_total_time(spans):
    intervals = [(D + timedelta(minutes=s), D + timedelta(minutes=s + n)) for s, n in spans]
    total = sum(n for _, n in spans)
    assert sum(minutes_by_day(intervals).values()) == total


def test_overlap_with_a_scheduled_window():
    block = (at(10), at(11))
    assert overlap_minutes([(at(9), at(10, 20))], block) == 20
    assert overlap_minutes([(at(10, 10), at(10, 40)), (at(10, 30), at(10, 50))], block) == 40
    assert overlap_minutes([(at(12), at(13))], block) == 0


def test_attendance_labels():
    block = (at(10), at(11))
    assert attendance([], block, at(9)) == "upcoming"
    assert attendance([], block, at(10, 30)) == "in_progress"
    assert attendance([], block, at(11, 5)) == "missed"
    assert attendance([(at(10), at(10, 20))], block, at(12)) == "partial"
    assert attendance([(at(10), at(10, 40))], block, at(12)) == "attended"


# ---------------- welfare flag lifecycle ----------------
from isd.engine.welfare import FlagRow, plan_flag_sync  # noqa: E402

T0 = datetime(2026, 3, 2, 9, 0, tzinfo=UTC)


def row(id, kind, status="open", raised=T0, acked=None, escalated=None):
    return FlagRow(id, kind, status, raised, acked, escalated)


def plan(detected, rows, now, suppress_days=3, escalate_minutes=720):
    return plan_flag_sync(set(detected), rows, now, suppress_days, escalate_minutes)


def test_a_new_condition_raises_a_flag_once():
    assert plan({"no_contact"}, [], T0) == [("raise", "no_contact", None)]
    assert plan({"no_contact"}, [row(1, "no_contact")], T0 + timedelta(minutes=5)) == []


def test_an_unacknowledged_flag_escalates_after_the_configured_time_and_only_once():
    r = row(1, "no_contact")
    assert plan({"no_contact"}, [r], T0 + timedelta(minutes=719)) == []
    assert plan({"no_contact"}, [r], T0 + timedelta(minutes=720)) == [("escalate", "no_contact", 1)]
    done = row(1, "no_contact", escalated=T0 + timedelta(hours=12))
    assert plan({"no_contact"}, [done], T0 + timedelta(days=3)) == []


def test_an_acknowledged_flag_stays_quiet_then_comes_back_if_the_condition_persists():
    r = row(1, "usage_drop", status="acknowledged", acked=T0)
    assert plan({"usage_drop"}, [r], T0 + timedelta(days=2)) == []
    assert plan({"usage_drop"}, [r], T0 + timedelta(days=3)) == [("raise", "usage_drop", None)]


def test_a_flag_whose_condition_is_gone_is_cleared_and_acknowledged_ones_too():
    assert plan(set(), [row(1, "no_contact")], T0) == [("clear", "no_contact", 1)]
    acked = row(2, "usage_drop", status="acknowledged", acked=T0)
    assert plan(set(), [acked], T0 + timedelta(hours=1)) == [("clear", "usage_drop", 2)]
    assert plan(set(), [row(3, "x", status="cleared")], T0) == []


def test_only_the_latest_flag_of_each_kind_counts():
    old = row(1, "no_contact", status="acknowledged", acked=T0)
    new = row(2, "no_contact", raised=T0 + timedelta(days=4))
    assert plan({"no_contact"}, [old, new], T0 + timedelta(days=4, minutes=1)) == []
