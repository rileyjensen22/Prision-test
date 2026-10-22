from datetime import UTC, datetime

from isd.analytics.rules import (
    assert_no_identifiers,
    band,
    cohort_label,
    cohort_labels_for_export,
    rate_per_100,
    summarize_cohort,
)


def test_cohort_is_a_calendar_quarter():
    assert cohort_label(datetime(2026, 1, 1, tzinfo=UTC)) == "2026-Q1"
    assert cohort_label(datetime(2026, 12, 31, tzinfo=UTC)) == "2026-Q4"


def test_band_never_gives_an_exact_count():
    assert band(0, (1, 5, 10)) == "0"
    assert band(3, (1, 5, 10)) == "1-4"
    assert band(5, (1, 5, 10)) == "5-9"
    assert band(40, (1, 5, 10)) == "10+"


def test_rate_per_100_handles_no_exposure():
    assert rate_per_100(3, 0) is None
    assert rate_per_100(3, 12) == 25.0


def test_small_cohorts_show_only_a_count_floor():
    rows = [
        {"tier_start": 1, "tier_now": 2, "courses": 1, "contacts": 10, "sanctions": 0, "weeks": 4}
    ] * 3
    out = summarize_cohort("2026-Q1", rows, minimum=5)
    assert out == {"cohort": "2026-Q1", "residents": "<5"}


def test_cohort_summary_numbers():
    rows = [
        {"tier_start": 1, "tier_now": 3, "courses": 2, "contacts": 8, "sanctions": 0, "weeks": 4},
        {"tier_start": 1, "tier_now": 1, "courses": 0, "contacts": 4, "sanctions": 1, "weeks": 4},
    ]
    out = summarize_cohort("2026-Q1", rows, minimum=2)
    assert out["residents"] == 2
    assert out["share_promoted"] == 0.5
    assert out["mean_tier_change"] == 1.0
    assert out["share_completed_a_course"] == 0.5
    assert out["contacts_per_week"] == 1.5
    assert out["sanctions_per_100_weeks"] == 12.5


def test_small_cohorts_are_merged_into_other_for_export():
    counts = {"2026-Q1": 12, "2026-Q2": 2}
    assert cohort_labels_for_export(counts, minimum=5) == {"2026-Q1": "2026-Q1", "2026-Q2": "OTHER"}


def test_identifier_scan_catches_codes_and_names():
    rows = [{"pseudonym": "S-abc", "cohort": "2026-Q1"}]
    assert_no_identifiers(rows, forbidden=["res-001", "Pat Example"])
    try:
        assert_no_identifiers([{"note": "see res-001"}], forbidden=["res-001"])
    except ValueError:
        pass
    else:
        raise AssertionError("identifier slipped through")
    try:
        assert_no_identifiers([{"resident_code": "x"}], forbidden=[])
    except ValueError:
        pass
    else:
        raise AssertionError("forbidden field slipped through")
