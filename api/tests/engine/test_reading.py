from hypothesis import given
from hypothesis import strategies as st

from isd.engine.reading import (
    BASELINE_CATALOGS,
    CATALOG_FEATURE,
    clamp_page,
    is_complete,
    paginate,
)


def test_paragraphs_become_pages_and_long_ones_split_on_sentences():
    assert paginate("One.\n\nTwo.") == ["One.", "Two."]
    text = "First sentence here. " * 30
    pages = paginate(text, max_chars=120)
    assert len(pages) > 1 and all(len(p) <= 120 for p in pages)


@given(st.text(min_size=1, max_size=3000), st.integers(40, 400))
def test_pagination_never_loses_text_or_makes_an_empty_page(text, size):
    pages = paginate(text, max_chars=size)
    assert all(p.strip() for p in pages)
    assert "".join("".join(p.split()) for p in pages) == "".join(text.split())


def test_page_clamping_and_completion():
    assert clamp_page(-3, 5) == 0 and clamp_page(99, 5) == 4 and clamp_page(2, 5) == 2
    assert not is_complete(3, 5) and is_complete(4, 5)


def test_every_catalog_maps_to_a_feature_and_legal_religious_are_the_baseline():
    assert CATALOG_FEATURE == {
        "general": "reading_general",
        "legal": "legal_materials",
        "religious": "religious_texts",
    }
    assert BASELINE_CATALOGS == {"legal", "religious"}
