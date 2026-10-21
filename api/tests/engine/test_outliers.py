import random

from hypothesis import given
from hypothesis import strategies as st

from isd.engine.outliers import StaffStats, find_outliers


def S(reports=0, sanctions=0, overturned=0, rejected=0):
    return StaffStats(reports, sanctions, overturned, rejected)


def test_identical_peers_flag_nobody():
    same = {f"o{i}": S(5, 4, 0, 1) for i in range(6)}
    assert all(not f for f in find_outliers(same).values())


def test_extreme_volume_is_flagged_and_peers_are_not():
    stats = {f"o{i}": S(4, 3) for i in range(5)} | {"heavy": S(30, 25)}
    flags = find_outliers(stats)
    assert {f.metric for f in flags["heavy"]} >= {"reports", "sanctions"}
    assert all(not flags[f"o{i}"] for i in range(5))


def test_high_overturn_rate_flagged_but_low_volume_is_not_rated():
    stats = {f"o{i}": S(6, 5, 0, 0) for i in range(5)}
    stats["bad"] = S(6, 5, 4, 0)  # 80% of its sanctions overturned
    stats["few"] = S(2, 2, 2, 0)  # 100% but only two sanctions: too few to judge
    flags = find_outliers(stats)
    assert any(f.metric == "overturn_rate" for f in flags["bad"])
    assert not any(f.metric == "overturn_rate" for f in flags["few"])


def test_rejection_rate_flag():
    stats = {f"o{i}": S(6, 5, 0, 0) for i in range(5)}
    stats["reckless"] = S(8, 2, 0, 6)
    assert any(f.metric == "rejection_rate" for f in find_outliers(stats)["reckless"])


def test_too_few_peers_flags_nobody():
    stats = {"a": S(30, 30), "b": S(1, 1), "c": S(1, 1)}
    assert all(not f for f in find_outliers(stats, min_peers=3).values())


def test_low_values_are_never_flagged():
    stats = {f"o{i}": S(20, 15) for i in range(5)} | {"quiet": S(0, 0)}
    assert find_outliers(stats)["quiet"] == []


@given(
    st.lists(
        st.tuples(st.integers(0, 40), st.integers(0, 40), st.integers(0, 40), st.integers(0, 40)),
        min_size=2,
        max_size=10,
    ),
    st.randoms(use_true_random=False),
)
def test_result_does_not_depend_on_order_and_flags_are_always_upward(rows, rnd):
    stats = {
        f"o{i}": S(r, min(s, r), min(o, min(s, r)), min(j, r))
        for i, (r, s, o, j) in enumerate(rows)
    }
    base = find_outliers(stats)
    items = list(stats.items())
    random.Random(rnd.random()).shuffle(items)
    assert find_outliers(dict(items)) == base
    for flags in base.values():
        assert all(f.z >= 2.0 and f.value > f.peer_mean for f in flags)
