from dataclasses import replace
from datetime import timedelta

from hypothesis import given, settings
from hypothesis import strategies as st

from isd.engine.entitlements import (
    DeviceLockFact,
    OffenseFact,
    ResidentFacts,
    SanctionFact,
    compute_entitlements,
)
from isd.engine.features import BASELINE_FEATURES, NON_BASELINE_FEATURES, SCOPES
from tests.engine.conftest import T0

OFFENSES = ["PLACEHOLDER_CATEGORY_A", "PLACEHOLDER_CATEGORY_B", "PLACEHOLDER_CATEGORY_C", "UNKNOWN"]


@st.composite
def sanctions(draw):
    start = T0 + timedelta(hours=draw(st.integers(-100, 100)))
    return SanctionFact(
        id=draw(st.integers(1, 99)),
        reason_code=draw(st.sampled_from(["DISRUPT", "CAM_BLOCK", "DEVICE_DAMAGE"])),
        scope=draw(st.sampled_from(sorted(SCOPES))),
        starts_at=start,
        ends_at=start + timedelta(hours=draw(st.integers(1, 200))),
    )


@st.composite
def facts(draw):
    return ResidentFacts(
        earned_tier=draw(st.integers(1, 10)),
        prior_returns=draw(st.integers(0, 30)),
        offenses=tuple(
            OffenseFact(c) for c in draw(st.lists(st.sampled_from(OFFENSES), max_size=3))
        ),
        sanctions=tuple(draw(st.lists(sanctions(), max_size=5))),
        blocked_contact_ids=tuple(draw(st.lists(st.integers(1, 9), max_size=3))),
        device_locks=tuple(
            DeviceLockFact(
                id=draw(st.integers(1, 99)),
                starts_at=T0 + timedelta(hours=draw(st.integers(-50, 50))),
                ends_at=T0 + timedelta(hours=draw(st.integers(51, 200))),
            )
            for _ in range(draw(st.integers(0, 2)))
        ),
    )


@settings(max_examples=300)
@given(facts())
def test_baseline_never_removed(cfg, f):
    e = compute_entitlements(f, cfg, T0)
    for feature in BASELINE_FEATURES:
        assert e.features[feature].allowed
        assert e.features[feature].reasons == ()
    assert e.features["out_of_cell_minimum"].limits["minutes_per_day"] >= 60


@settings(max_examples=300)
@given(facts())
def test_every_lock_has_reason_and_appeal_path(cfg, f):
    e = compute_entitlements(f, cfg, T0)
    for feature in NON_BASELINE_FEATURES:
        fe = e.features[feature]
        assert fe.allowed != bool(fe.reasons) or (not fe.allowed and fe.reasons)
        if not fe.allowed:
            assert fe.reasons, feature
            assert all(r.code and r.how_to_appeal for r in fe.reasons)
        else:
            assert not fe.reasons


@settings(max_examples=200)
@given(facts(), sanctions())
def test_adding_a_sanction_never_grants_more(cfg, f, extra):
    before = compute_entitlements(f, cfg, T0)
    more = replace(f, sanctions=f.sanctions + (extra,))
    after = compute_entitlements(more, cfg, T0)
    for feature in NON_BASELINE_FEATURES:
        assert after.allowed(feature) <= before.allowed(feature)


@settings(max_examples=200)
@given(facts())
def test_effective_tier_respects_ceiling(cfg, f):
    e = compute_entitlements(f, cfg, T0)
    assert e.effective_tier <= e.ceiling_tier and e.effective_tier <= e.earned_tier
    capped = compute_entitlements(
        ResidentFacts(e.effective_tier, 0), cfg, T0
    )  # same grants as a resident whose tier equals the effective tier
    uncapped = compute_entitlements(ResidentFacts(f.earned_tier, f.prior_returns), cfg, T0)
    for feature in NON_BASELINE_FEATURES:
        assert uncapped.allowed(feature) == capped.allowed(feature)


def test_seed_matrix(cfg):
    t1 = compute_entitlements(ResidentFacts(1, 0), cfg, T0)
    assert t1.features["calls"].limits == {"minutes_per_day": 15}
    assert not t1.allowed("texting") and not t1.allowed("chess")
    assert t1.features["texting"].reasons[0].code == "TIER_LOCKED"
    t10 = compute_entitlements(ResidentFacts(10, 0), cfg, T0)
    assert t10.features["calls"].limits == {"minutes_per_day": 90}
    assert t10.features["outdoor_rec"].limits == {"minutes_per_day": 120}
    assert t10.features["video"].limits == {"minutes_per_week": 180}


def test_ceiling_reason_and_sanction_reason_with_end_time(cfg):
    capped = compute_entitlements(ResidentFacts(10, 12), cfg, T0)  # ceiling tier 1
    assert capped.effective_tier == 1
    assert capped.features["texting"].reasons[0].code == "TIER_CEILING"
    s = SanctionFact(
        7, "DISRUPT", "communication", T0 - timedelta(hours=1), T0 + timedelta(hours=23)
    )
    e = compute_entitlements(ResidentFacts(10, 0, sanctions=(s,)), cfg, T0)
    r = e.features["calls"].reasons[0]
    assert (r.code, r.ends_at, r.how_to_appeal, r.ref_id) == ("DISRUPT", s.ends_at, "appeal", 7)
    assert e.allowed("commissary") and e.allowed("attorney_calls")
    assert e.next_change_at == s.ends_at
    after = compute_entitlements(ResidentFacts(10, 0, sanctions=(s,)), cfg, s.ends_at)
    assert after.allowed("calls")


def test_offense_restriction_never_blocks_baseline(cfg):
    e = compute_entitlements(ResidentFacts(10, 0, offenses=(OffenseFact(OFFENSES[0]),)), cfg, T0)
    assert not e.allowed("video") and e.features["video"].reasons[0].code == "OFFENSE_RESTRICTION"
    assert e.allowed("legal_materials")
