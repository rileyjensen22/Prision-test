"""A staff device lock pauses every non-baseline feature, with a reason and an end time."""

from datetime import timedelta

from hypothesis import given, settings
from hypothesis import strategies as st

from isd.engine.entitlements import DeviceLockFact, ResidentFacts, compute_entitlements
from isd.engine.features import ASK_STAFF, BASELINE_FEATURES, NON_BASELINE_FEATURES
from tests.engine.conftest import T0


def lock(start_h=-1, end_h=5):
    return DeviceLockFact(
        id=7, starts_at=T0 + timedelta(hours=start_h), ends_at=T0 + timedelta(hours=end_h)
    )


def test_an_active_lock_pauses_every_non_baseline_feature_with_a_reason(cfg):
    ent = compute_entitlements(
        ResidentFacts(earned_tier=10, prior_returns=0, device_locks=(lock(),)), cfg, T0
    )
    for name in NON_BASELINE_FEATURES:
        fe = ent.features[name]
        assert not fe.allowed
        reason = next(r for r in fe.reasons if r.source == "device")
        assert reason.code == "DEVICE_LOCK"
        assert reason.ends_at == T0 + timedelta(hours=5)  # invariant 5: an end time
        assert reason.how_to_appeal == ASK_STAFF  # and a way to reach someone


def test_the_baseline_never_locks(cfg):
    ent = compute_entitlements(
        ResidentFacts(earned_tier=1, prior_returns=30, device_locks=(lock(),)), cfg, T0
    )
    assert all(ent.features[name].allowed for name in BASELINE_FEATURES)


def test_a_lock_that_has_not_started_or_has_ended_does_nothing(cfg):
    for locks in ((lock(2, 6),), (lock(-6, -1),)):
        ent = compute_entitlements(
            ResidentFacts(earned_tier=10, prior_returns=0, device_locks=locks), cfg, T0
        )
        assert ent.features["calls"].allowed


def test_the_lock_end_is_the_next_change_so_clients_refresh(cfg):
    ent = compute_entitlements(
        ResidentFacts(earned_tier=10, prior_returns=0, device_locks=(lock(),)), cfg, T0
    )
    assert ent.next_change_at == T0 + timedelta(hours=5)


@settings(max_examples=60, deadline=None)
@given(
    tier=st.integers(1, 10),
    returns=st.integers(0, 30),
    start=st.integers(-100, 100),
    length=st.integers(1, 200),
)
def test_no_lock_ever_touches_the_baseline(cfg, tier, returns, start, length):
    facts = ResidentFacts(
        earned_tier=tier, prior_returns=returns, device_locks=(lock(start, start + length),)
    )
    ent = compute_entitlements(facts, cfg, T0)
    assert all(ent.features[name].allowed for name in BASELINE_FEATURES)
