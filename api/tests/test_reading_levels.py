"""Reading level and language really change what a resident reads, in the reader and in courses."""

import pytest

from isd.config_loader import load_config
from isd.engine.config import validate_reading
from isd.engine.reading import pick_variant
from isd.models import Resident
from isd.services import education, reading
from tests.conftest import NOW

ITEM = {
    "id": "x", "title": "T", "author": "A", "catalog": "general", "source": "s",
    "language": "en", "text": "standard english",
    "variants": [
        {"language": "es", "reading_level": "standard", "title": "T-es", "text": "estandar"},
        {"language": "en", "reading_level": "simple", "text": "easy english"},
    ],
}  # fmt: skip


def test_the_best_match_is_chosen_in_a_fixed_order():
    assert pick_variant(ITEM, "en", "standard")["text"] == "standard english"
    assert pick_variant(ITEM, "en", "simple")["text"] == "easy english"
    es = pick_variant(ITEM, "es", "standard")
    assert (es["text"], es["title"], es["language"]) == ("estandar", "T-es", "es")
    # Spanish simple is not written: fall back to Spanish standard, not to English
    assert pick_variant(ITEM, "es", "simple")["text"] == "estandar"
    # an unknown level behaves like standard; an unknown language falls back to English
    assert pick_variant(ITEM, "en", "weird")["text"] == "standard english"
    assert pick_variant(ITEM, "fr", "simple")["text"] == "easy english"
    assert pick_variant(ITEM, "es", "standard")["reading_level"] == "standard"
    assert pick_variant(ITEM, "en", "simple")["reading_level"] == "simple"


def test_the_validator_rejects_bad_or_duplicate_variants():
    base = {"items": [dict(ITEM)]}
    validate_reading(base)
    for bad in (
        [{"language": "fr", "reading_level": "simple", "text": "x"}],
        [{"language": "es", "reading_level": "expert", "text": "x"}],
        [{"language": "en", "reading_level": "standard", "text": "x"}],  # same as the item itself
        [{"language": "es", "reading_level": "simple", "text": " "}],
    ):
        with pytest.raises(ValueError):
            validate_reading({"items": [{**ITEM, "variants": bad}]})


def test_the_shipped_config_has_spanish_for_every_text_and_an_easy_version_of_the_fables():
    items = {i["id"]: i for i in load_config()["reading"]["items"]}
    for iid, item in items.items():
        langs = {(v["language"], v["reading_level"]) for v in item.get("variants", [])}
        assert ("es", "standard") in langs, f"{iid} has no Spanish version"
    for iid in ("tortoise-hare", "lion-mouse"):
        langs = {(v["language"], v["reading_level"]) for v in items[iid]["variants"]}
        assert {("en", "simple"), ("es", "simple")} <= langs
    # protected texts carry a plain label that the Spanish is unofficial where it is a translation
    legal = next(v for v in items["bill-of-rights-selected"]["variants"] if v["language"] == "es")
    assert "no oficial" in legal["author"].lower()


def test_the_reader_follows_the_residents_language_and_level(
    owner, seeded, make_resident, reference_data
):
    rid = make_resident()
    r = owner.get(Resident, rid)
    standard = reading.read_item(owner, rid, "tortoise-hare", NOW)
    r.reading_level = "simple"
    simple = reading.read_item(owner, rid, "tortoise-hare", NOW)
    assert simple["reading_level"] == "simple" and simple["text"] != standard["text"]
    assert len(simple["text"]) < len(standard["text"]) + 50 and len(simple["pages"]) >= 1
    r.language, r.reading_level = "es", "standard"
    es = reading.read_item(owner, rid, "psalm-23", NOW)
    assert es["language"] == "es" and "Jehová" in es["text"]
    listing = {i["id"]: i for i in reading.list_items(owner, rid, NOW)}
    assert listing["psalm-23"]["language"] == "es" and listing["tortoise-hare"]["title"].startswith(
        "La liebre"
    )


def test_courses_use_the_simple_lesson_text_for_a_simple_reader(owner, seeded, make_resident):
    rid = make_resident()
    r = owner.get(Resident, rid)
    standard = education.get_course(owner, rid, "LIT101", NOW)
    r.reading_level = "simple"
    simple = education.get_course(owner, rid, "LIT101", NOW)
    a, b = standard["lessons"][0]["body"]["en"], simple["lessons"][0]["body"]["en"]
    assert a != b
