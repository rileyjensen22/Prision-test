from hypothesis import given
from hypothesis import strategies as st

from isd.engine.ceiling import ceiling_tier, raw_loss


def test_spec_values():
    assert [ceiling_tier(n) for n in range(1, 13)] == [10, 9, 9, 8, 7, 6, 6, 5, 4, 2, 1, 1]
    assert ceiling_tier(0) == 10


@given(st.integers(0, 60), st.floats(5, 30), st.floats(1.1, 3))
def test_ceiling_is_non_increasing_and_bounded(n, N, p):
    assert 1 <= ceiling_tier(n, N, p) <= 10
    assert ceiling_tier(n + 1, N, p) <= ceiling_tier(n, N, p)


@given(st.integers(0, 40), st.floats(5, 30), st.floats(1.1, 3))
def test_raw_loss_per_step_grows(n, N, p):
    first = raw_loss(n + 1, N, p) - raw_loss(n, N, p)
    second = raw_loss(n + 2, N, p) - raw_loss(n + 1, N, p)
    assert second >= first - 1e-9
