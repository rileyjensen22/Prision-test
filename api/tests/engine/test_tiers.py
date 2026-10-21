from datetime import timedelta

from hypothesis import given
from hypothesis import strategies as st

from isd.engine.tiers import demotion_threshold, evaluate_tier, tier_for_points
from tests.engine.conftest import T0

steps = st.lists(
    st.tuples(st.integers(0, 3 * 86400), st.integers(0, 4000)), min_size=1, max_size=60
)


def test_thresholds(cfg):
    assert tier_for_points(0, cfg.thresholds) == 1
    assert tier_for_points(100, cfg.thresholds) == 2
    assert tier_for_points(99, cfg.thresholds) == 1
    assert tier_for_points(99999, cfg.thresholds) == 10


def test_hysteresis_no_flicker_at_threshold(cfg):
    d = evaluate_tier(1, 100, cfg, None, T0)
    assert (d.tier, d.direction) == (2, "up")
    # Slightly below the promotion threshold: stays at tier 2.
    assert evaluate_tier(2, 99, cfg, None, T0).direction == "same"
    assert evaluate_tier(2, 86, cfg, None, T0).direction == "same"  # 85 is the demotion line
    assert evaluate_tier(2, 84, cfg, None, T0).tier == 1


def test_demotion_threshold_below_promotion(cfg):
    for t in range(2, 11):
        assert demotion_threshold(t, cfg) < cfg.thresholds[t - 1]


@given(steps)
def test_at_most_one_level_per_drop_and_one_drop_per_7_days(cfg_steps):
    from isd.config_loader import load_config
    from isd.engine.config import EngineConfig

    cfg = EngineConfig.from_sections(load_config())
    tier, now, last_drop, drops = 1, T0, None, []
    for gap, points in cfg_steps:
        now += timedelta(seconds=gap)
        d = evaluate_tier(tier, points, cfg, last_drop, now)
        if d.direction == "down":
            assert d.tier == tier - 1
            drops.append(now)
            last_drop = now
        elif d.direction == "up":
            assert d.tier > tier
        tier = d.tier
    for a, b in zip(drops, drops[1:], strict=False):
        assert b - a >= timedelta(days=7)


@given(st.integers(2, 10))
def test_cannot_drop_twice_in_window_even_at_zero_points(tier):
    from isd.config_loader import load_config
    from isd.engine.config import EngineConfig

    cfg = EngineConfig.from_sections(load_config())
    first = evaluate_tier(tier, 0, cfg, None, T0)
    assert first.tier == tier - 1
    again = evaluate_tier(first.tier, 0, cfg, T0, T0 + timedelta(days=6, hours=23))
    assert again.tier == first.tier
    if first.tier > 1:
        later = evaluate_tier(first.tier, 0, cfg, T0, T0 + timedelta(days=7))
        assert later.tier == first.tier - 1
