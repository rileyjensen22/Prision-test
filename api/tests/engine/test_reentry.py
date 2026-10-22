from datetime import date

import pytest

from isd.engine.reentry import (
    CHECKLIST_STATUSES,
    checklist_progress,
    countdown,
    latest_statuses,
    validate_reentry,
)

ITEMS = [{"code": "ID_DOCUMENTS"}, {"code": "HOUSING"}, {"code": "EMPLOYMENT"}]


def cfg(**over):
    base = {
        "version": 1,
        "checklist": [
            {
                "code": "ID_DOCUMENTS",
                "title": {"en": "ID", "es": "ID"},
                "detail": {"en": "x", "es": "x"},
            },
            {"code": "HOUSING", "title": {"en": "H", "es": "H"}, "detail": {"en": "x", "es": "x"}},
        ],
        "courses": ["REENTRY301"],
        "resources": [
            {
                "code": "R1",
                "category": "housing",
                "title": {"en": "A", "es": "A"},
                "description": {"en": "d", "es": "d"},
                "phone": "555-0100",
                "languages": ["en"],
            }
        ],
    }
    base.update(over)
    return base


def test_countdown_counts_days_and_stops_at_zero():
    today = date(2026, 3, 1)
    assert countdown(None, today) is None
    assert countdown(date(2026, 3, 11), today) == {
        "release_date": "2026-03-11",
        "days_left": 10,
        "weeks_left": 1,
    }
    assert countdown(date(2026, 3, 1), today)["days_left"] == 0
    assert countdown(date(2026, 2, 1), today)["days_left"] == 0  # a past date never goes negative


def test_latest_status_wins_and_unknown_items_are_ignored():
    events = [
        ("HOUSING", "in_progress"),
        ("HOUSING", "done"),
        ("ID_DOCUMENTS", "todo"),
        ("OTHER", "done"),
    ]
    assert latest_statuses(events, ITEMS) == {
        "ID_DOCUMENTS": "todo",
        "HOUSING": "done",
        "EMPLOYMENT": "todo",
    }


def test_progress_counts_not_needed_as_resolved():
    statuses = {"ID_DOCUMENTS": "done", "HOUSING": "not_needed", "EMPLOYMENT": "in_progress"}
    assert checklist_progress(statuses) == {"done": 1, "resolved": 2, "total": 3}
    assert set(CHECKLIST_STATUSES) == {"todo", "in_progress", "done", "not_needed"}


def test_valid_config_passes():
    validate_reentry(cfg(), {"REENTRY301"})


@pytest.mark.parametrize(
    "bad",
    [
        {"checklist": []},
        {"courses": ["NOPE"]},
        {"resources": [{"code": "R1"}]},
        {
            "checklist": [
                {"code": "A b", "title": {"en": "x", "es": "x"}, "detail": {"en": "x", "es": "x"}}
            ]
        },
    ],
)
def test_bad_config_is_refused(bad):
    with pytest.raises(ValueError):
        validate_reentry(cfg(**bad), {"REENTRY301"})


def test_resource_phone_must_be_a_synthetic_number():
    resource = cfg()["resources"][0] | {"phone": "404-555-0100"}
    with pytest.raises(ValueError, match="synthetic"):
        validate_reentry(cfg(resources=[resource]), {"REENTRY301"})


def test_duplicate_codes_are_refused():
    item = cfg()["checklist"][0]
    with pytest.raises(ValueError, match="duplicate"):
        validate_reentry(cfg(checklist=[item, item]), {"REENTRY301"})
