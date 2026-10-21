from datetime import timedelta

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from isd.engine.entitlements import OffenseFact, ResidentFacts, SanctionFact, compute_entitlements
from isd.engine.features import BASELINE_FEATURES, NON_BASELINE_FEATURES
from isd.engine.mirror import (
    PRIVATE_SCREEN_PREFIXES,
    REDACTED_PATH,
    is_valid_screen_path,
    redaction_reason,
)
from isd.engine.sandbox import (
    SandboxOverrides,
    SandboxSanction,
    apply_to_facts,
    apply_to_settings,
    validate,
)
from tests.engine.conftest import T0

REAL = ResidentFacts(
    earned_tier=3,
    prior_returns=2,
    offenses=(OffenseFact("PLACEHOLDER_CATEGORY_A"),),
    sanctions=(
        SanctionFact(
            9, "DISRUPT", "communication", T0 - timedelta(hours=1), T0 + timedelta(hours=5)
        ),
    ),
)


def test_no_overrides_changes_nothing(cfg):
    assert apply_to_facts(REAL, SandboxOverrides(), cfg, T0) == REAL


def test_overrides_replace_only_what_was_asked(cfg):
    out = apply_to_facts(REAL, SandboxOverrides(tier=8, prior_returns=0), cfg, T0)
    assert (out.earned_tier, out.prior_returns) == (8, 0)
    assert out.sanctions == REAL.sanctions and out.offenses == REAL.offenses


def test_clear_and_add_sanctions_and_offenses(cfg):
    ov = SandboxOverrides(
        clear_sanctions=True,
        offense_categories=("PLACEHOLDER_CATEGORY_B",),
        add_sanctions=(SandboxSanction("CAM_BLOCK", hours_remaining=10),),
    )
    out = apply_to_facts(REAL, ov, cfg, T0)
    (s,) = out.sanctions
    assert s.id < 0 and s.ends_at == T0 + timedelta(hours=10)
    assert s.starts_at == s.ends_at - timedelta(hours=48) and s.starts_at <= T0 < s.ends_at
    assert [o.category for o in out.offenses] == ["PLACEHOLDER_CATEGORY_B"]
    e = compute_entitlements(out, cfg, T0)
    assert not e.allowed("calls") and e.allowed("legal_materials")
    assert e.features["calls"].reasons[0].code == "CAM_BLOCK"


def test_validation(cfg):
    bad = [
        SandboxOverrides(tier=0),
        SandboxOverrides(tier=11),
        SandboxOverrides(prior_returns=-1),
        SandboxOverrides(prior_returns=999),
        SandboxOverrides(offense_categories=("NOPE",)),
        SandboxOverrides(add_sanctions=(SandboxSanction("NOPE"),)),
        SandboxOverrides(add_sanctions=(SandboxSanction("DISRUPT", hours_remaining=25),)),
        SandboxOverrides(add_sanctions=(SandboxSanction("DISRUPT", hours_remaining=0),)),
    ]
    for ov in bad:
        with pytest.raises(ValueError):
            validate(ov, cfg)


def test_settings_overrides():
    base = {"language": "en", "text_size": "normal", "reading_level": "standard", "captions": False}
    out = apply_to_settings(base, SandboxOverrides(language="es", captions=True))
    assert out == {**base, "language": "es", "captions": True} and base["language"] == "en"


@st.composite
def overrides(draw):
    return SandboxOverrides(
        tier=draw(st.none() | st.integers(1, 10)),
        prior_returns=draw(st.none() | st.integers(0, 60)),
        offense_categories=draw(
            st.none()
            | st.lists(
                st.sampled_from(
                    ["PLACEHOLDER_CATEGORY_A", "PLACEHOLDER_CATEGORY_B", "PLACEHOLDER_CATEGORY_C"]
                ),
                max_size=3,
            ).map(tuple)
        ),
        add_sanctions=tuple(
            draw(
                st.lists(
                    st.sampled_from(
                        [
                            "DISRUPT",
                            "CELL_MESS",
                            "STAFF_DISRESPECT",
                            "CAM_BLOCK",
                            "DEVICE_TAMPER",
                            "DEVICE_DAMAGE",
                        ]
                    ).map(SandboxSanction),
                    max_size=4,
                )
            )
        ),
        clear_sanctions=draw(st.booleans()),
    )


@settings(max_examples=300)
@given(overrides())
def test_no_override_can_ever_remove_the_baseline(cfg, ov):
    e = compute_entitlements(apply_to_facts(REAL, ov, cfg, T0), cfg, T0)
    assert all(e.features[f].allowed and not e.features[f].reasons for f in BASELINE_FEATURES)
    for f in NON_BASELINE_FEATURES:
        fe = e.features[f]
        assert fe.allowed or fe.reasons  # every simulated lock still has a reason


# ---- mirror redaction ----
def test_private_screens_and_calls_are_redacted():
    assert redaction_reason("/resident", False) is None
    assert redaction_reason("/resident/tier", False) is None
    assert redaction_reason("/resident/feature/calls", False) is None
    assert redaction_reason("/resident/feature/calls", True) == "PRIVILEGED_CALL"
    assert redaction_reason(None, True) == "PRIVILEGED_CALL"
    assert redaction_reason(REDACTED_PATH, False) == "PRIVATE_SCREEN"
    for p in PRIVATE_SCREEN_PREFIXES:
        assert redaction_reason(p, False) == "PRIVATE_SCREEN"
        assert redaction_reason(p + "/anything", False) == "PRIVATE_SCREEN"
    assert redaction_reason("/resident/feature/legal_materials_extra", False) is None


@given(st.sampled_from(PRIVATE_SCREEN_PREFIXES), st.text(alphabet="abcdefg_-", max_size=12))
def test_anything_under_a_private_screen_is_redacted(prefix, tail):
    path = prefix + ("/" + tail if tail else "")
    assert redaction_reason(path, False) is not None


def test_screen_path_validation():
    assert is_valid_screen_path("/resident") and is_valid_screen_path("/resident/feature/calls")
    for bad in (
        "/staff",
        "resident",
        "/resident/../x",
        "/resident?x=1",
        "/resident//a",
        "/resident/" + "a" * 120,
        "javascript:alert(1)",
    ):
        assert not is_valid_screen_path(bad)
