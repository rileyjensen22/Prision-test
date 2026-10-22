import pytest
from hypothesis import given
from hypothesis import strategies as st

from isd.engine.contacts import ContactInvalid, can_review, clean_request
from isd.engine.monitoring import match_rules, validate_monitoring

RULES = [
    {"id": "R1", "label": "Demo one", "keywords": ["demo alpha", "Bravo"]},
    {"id": "R2", "label": "Demo two", "keywords": ["charlie"]},
]


def test_matching_ignores_case_accents_spacing_and_word_parts():
    assert [r["id"] for r in match_rules("Say DEMO   ALPHA now", RULES)] == ["R1"]
    assert [r["id"] for r in match_rules("brávo!", RULES)] == ["R1"]
    assert match_rules("charliehorse and bravos", RULES) == []  # not whole words
    assert [r["id"] for r in match_rules("charlie, bravo", RULES)] == ["R1", "R2"]
    assert match_rules("nothing here", RULES) == []


@given(st.text(max_size=500))
def test_matching_never_fails_and_only_returns_known_rules(text):
    assert {r["id"] for r in match_rules(text, RULES)} <= {"R1", "R2"}


def test_a_rule_needs_an_id_a_label_and_keywords():
    validate_monitoring({"version": 1, "rules": RULES, "text_max_chars": 500})
    for bad in (
        {"rules": [{"id": "A", "label": "x", "keywords": []}], "text_max_chars": 500},
        {"rules": [{"id": "A", "label": "", "keywords": ["k"]}], "text_max_chars": 500},
        {"rules": RULES + RULES, "text_max_chars": 500},  # duplicate ids
        {"rules": RULES, "text_max_chars": 0},
    ):
        with pytest.raises(ValueError):
            validate_monitoring(bad)


def test_contact_requests_are_cleaned_and_bad_ones_refused():
    assert clean_request("  Sam Rivera ", "friend", "(555) 010-0199") == (
        "Sam Rivera",
        "friend",
        "(555) 010-0199",
    )
    for name, kind, phone, code in (
        ("S", "friend", "555-0100", "BAD_NAME"),
        ("Sam", "enemy", "555-0100", "BAD_TYPE"),
        ("Sam", "friend", "not a number", "BAD_NUMBER"),
        ("Sam", "friend", "12", "BAD_NUMBER"),
    ):
        with pytest.raises(ContactInvalid) as e:
            clean_request(name, kind, phone)
        assert e.value.code == code


def test_who_may_approve_which_contact():
    assert can_review("officer", "family") and can_review("officer", "friend")
    assert not can_review("officer", "attorney")  # attorney contacts need a supervisor
    assert can_review("supervisor", "attorney") and can_review("admin", "attorney")
    assert not can_review("auditor", "family")
