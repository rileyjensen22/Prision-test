import pytest
from hypothesis import given
from hypothesis import strategies as st

from isd.work_rules import (
    TASK_KINDS,
    contains_personal_data,
    public_view,
    review_answer,
    similarity,
    split_pay,
    validate_task_spec,
)

TRANSCRIBE = {
    "scan": "A hare 1aughed at a t0rtoise.",
    "expected": "A hare laughed at a tortoise.",
    "source": "Aesop (public domain)",
}
CAPTION = {
    "scene": "A person counts coins into three equal piles.",
    "keywords": ["coins", "piles", "count"],
    "source": "Synthetic course clip",
}
LABEL = {
    "item": "What time is it?",
    "options": ["statement", "question", "exclamation"],
    "expected": "question",
    "source": "Synthetic sentence",
}


@given(st.integers(0, 10_000_000), st.integers(0, 100), st.integers(0, 100))
def test_a_split_always_adds_up_and_the_remainder_goes_to_the_resident(gross, fac, ded):
    if fac + ded > 100:
        fac, ded = 100 - ded, ded
    resident, facility, deductions = split_pay(gross, 100 - fac - ded, fac, ded)
    assert resident + facility + deductions == gross
    assert min(resident, facility, deductions) >= 0
    assert facility == gross * fac // 100 and deductions == gross * ded // 100


def test_the_seed_split_of_100_cents():
    assert split_pay(100, 60, 30, 10) == (60, 30, 10)
    assert split_pay(15, 60, 30, 10) == (
        10,
        4,
        1,
    )  # 15c: 4 to facility, 1 to deductions, rest to you


def test_bad_splits_are_refused():
    for bad in ((60, 30, 20), (-1, 51, 50), (50, 50, 1)):
        with pytest.raises(ValueError):
            split_pay(100, *bad)


@pytest.mark.parametrize(
    "text",
    [
        "write to sam@example.com",
        "call 404-555-0134 tonight",
        "(404) 555 0134",
        "ssn 123-45-6789",
        "account 4111 1111 1111 1111",
        "12 Oak Street, Atlanta",
        "born on 03/14/1988",
    ],
)
def test_personal_data_is_recognised(text):
    assert contains_personal_data(text)


@pytest.mark.parametrize(
    "text",
    [
        "A hare laughed at a tortoise.",
        "Four score and seven years ago",
        "In 1787 the delegates met",
        "Chapter 12, page 340",
        "",
    ],
)
def test_ordinary_text_is_not_flagged(text):
    assert not contains_personal_data(text)


def test_task_specs_are_validated_for_shape_and_screened():
    for kind, spec in (
        ("transcription_public_domain", TRANSCRIBE),
        ("captioning", CAPTION),
        ("labeling_non_personal", LABEL),
    ):
        validate_task_spec(kind, spec)
    with pytest.raises(ValueError):
        validate_task_spec("customer_support", TRANSCRIBE)
    with pytest.raises(ValueError):
        validate_task_spec("captioning", {"scene": "x"})  # missing keywords and source
    with pytest.raises(ValueError, match="personal"):
        validate_task_spec("captioning", {**CAPTION, "scene": "Call Pat on 404-555-0134"})
    with pytest.raises(ValueError):
        validate_task_spec("labeling_non_personal", {**LABEL, "expected": "other"})
    assert set(TASK_KINDS) == {
        "transcription_public_domain",
        "captioning",
        "labeling_non_personal",
    }


def test_what_the_device_sees_never_includes_the_answer():
    assert "expected" not in public_view("transcription_public_domain", TRANSCRIBE)
    assert "keywords" not in public_view("captioning", CAPTION)
    seen = public_view("labeling_non_personal", LABEL)
    assert "expected" not in seen and seen["options"] == LABEL["options"]


def test_reviewing_answers():
    t = "transcription_public_domain"
    assert review_answer(t, TRANSCRIBE, "A hare laughed at a tortoise.", 0.9).accepted
    assert review_answer(t, TRANSCRIBE, "a hare  laughed at a tortoise", 0.9).accepted
    assert not review_answer(t, TRANSCRIBE, "something else entirely", 0.9).accepted
    assert review_answer("captioning", CAPTION, "Someone counts coins into piles", 0.9).accepted
    assert not review_answer("captioning", CAPTION, "ok", 0.9).accepted
    assert not review_answer("captioning", CAPTION, "A dog runs in a park today", 0.9).accepted
    assert review_answer("labeling_non_personal", LABEL, "question", 0.9).accepted
    assert not review_answer("labeling_non_personal", LABEL, "statement", 0.9).accepted
    bad = review_answer("captioning", CAPTION, "coins piles call 404-555-0134", 0.9)
    assert not bad.accepted and bad.reason == "PERSONAL_DATA"


@given(st.text(max_size=200), st.text(max_size=200))
def test_similarity_is_between_zero_and_one_and_symmetric_for_equal_text(a, b):
    assert 0 <= similarity(a, b) <= 1
    assert similarity(a, a) == 1
