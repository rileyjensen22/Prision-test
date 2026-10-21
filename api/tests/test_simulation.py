"""A week of synthetic activity through the real services, then every invariant checked."""

import pytest
from sqlalchemy import create_engine

from isd.simulation import SimConfig, run_simulation
from tests.conftest import make_database


@pytest.fixture(scope="module")
def sim_report():
    engine = create_engine(make_database("isd_simtest"))
    report = run_simulation(engine, SimConfig(seed=1, residents=12, days=7))
    engine.dispose()
    return report


def test_every_invariant_holds_after_a_simulated_week(sim_report):
    failed = [(c.name, c.detail) for c in sim_report.checks if not c.passed]
    assert failed == []
    assert len(sim_report.checks) >= 18  # none of the checks quietly disappeared


def test_the_simulation_really_exercised_the_system(sim_report):
    assert sim_report.summary["not_exercised"] == []
    counts = sim_report.counts
    assert counts["call"] > 20 and counts["order"] > 5 and counts["sanction_issue"] > 20
    assert counts["appeal_review"] > 5 and counts["daily_clean_days"] > 20
    # the rules said no, many times, in the ways they should
    denied = sim_report.denied
    assert denied["call:FEATURE_LOCKED"] + denied["call:CONTACT_UNAVAILABLE"] > 0
    assert denied["text:FEATURE_LOCKED"] + denied["order:ITEM_TIER"] > 0
    assert sim_report.summary["audit_entries"] > 300
    assert sim_report.summary["calls"]["attorney"] > 0


def test_same_seed_same_week():
    a = create_engine(make_database("isd_simtest_a"))
    b = create_engine(make_database("isd_simtest_b"))
    cfg = SimConfig(seed=7, residents=6, days=3)
    ra, rb = run_simulation(a, cfg), run_simulation(b, cfg)
    assert ra.passed and rb.passed
    assert ra.counts == rb.counts and ra.denied == rb.denied
    assert (
        ra.summary["sanctions"] == rb.summary["sanctions"]
        and ra.summary["ledger"] == rb.summary["ledger"]
    )
    a.dispose(), b.dispose()
