"""Phase 10: reading. Baseline texts never lock; progress moves forward; points are optional."""

from datetime import timedelta

import pytest
from sqlalchemy import select

from isd.engine.authority import Evidence
from isd.models import AuditLog, PointEvent, ReadingLog
from isd.services import reading, sanctions
from isd.services.audit import SYSTEM, Actor
from isd.services.config_store import get_current, set_config
from tests.conftest import NOW
from tests.test_phase7_services import give

BASELINE = ("bill-of-rights-selected", "psalm-23", "dhammapada-twin-verses")


def lock_everything(owner, rid, make_staff):
    officer, sup = make_staff("officer"), make_staff("supervisor")
    colleague = make_staff("officer")
    s = sanctions.issue_sanction(
        owner,
        officer,
        rid,
        "CAM_BLOCK",
        NOW,
        Evidence("second_staff_report", reporter_id=colleague.id),
    )
    sanctions.confirm_sanction(owner, sup, s.id, NOW + timedelta(minutes=1))
    return NOW + timedelta(hours=1)


def listing(owner, rid, at):
    return {i["id"]: i for i in reading.list_items(owner, rid, at)}


def test_catalog_has_paged_texts_and_the_baseline_ones(
    owner, seeded, reference_data, make_resident
):
    items = listing(owner, make_resident(), NOW)
    assert set(BASELINE) <= set(items)
    assert all(items[b]["allowed"] and items[b]["pages"] >= 1 for b in BASELINE)
    assert {items[b]["catalog"] for b in BASELINE} == {"legal", "religious"}
    assert items["bill-of-rights-selected"]["pages"] == 3


def test_baseline_reading_survives_every_sanction_but_general_reading_does_not(
    owner, seeded, reference_data, make_resident, make_staff
):
    rid = make_resident()
    give(owner, rid, 450)  # tier 4: the expanded catalog is open
    assert listing(owner, rid, NOW)["preamble"]["allowed"]
    later = lock_everything(owner, rid, make_staff)
    items = listing(owner, rid, later)
    assert not items["tortoise-hare"]["allowed"] and not items["preamble"]["allowed"]
    assert items["tortoise-hare"]["reasons"][0]["code"] == "CAM_BLOCK"
    for b in BASELINE:
        assert items[b]["allowed"]
        assert reading.read_item(owner, rid, b, later)["pages"]
    with pytest.raises(reading.ReadingDenied) as e:
        reading.read_item(owner, rid, "tortoise-hare", later)
    assert e.value.code == "FEATURE_LOCKED"


def test_the_allow_list_governs_general_texts_and_cannot_remove_baseline_ones(
    owner, seeded, reference_data, make_resident, make_staff
):
    rid, admin = make_resident(), Actor(make_staff("admin").id, "admin")
    sources = {s.name: s for s in reading.list_sources(owner)}
    reading.set_source_active(owner, admin, sources["Bundled public-domain texts"].id, False)
    items = listing(owner, rid, NOW)
    assert not items["tortoise-hare"]["allowed"]
    assert all(items[b]["allowed"] for b in BASELINE)
    with pytest.raises(reading.ReadingDenied) as e:
        reading.read_item(owner, rid, "tortoise-hare", NOW)
    assert e.value.code == "SOURCE_NOT_APPROVED"
    with pytest.raises(ValueError, match="protected"):
        reading.set_source_active(owner, admin, sources["Bundled baseline texts"].id, False)
    assert reading.read_item(owner, rid, "psalm-23", NOW)["title"].startswith("Psalm")


def test_every_text_comes_from_a_listed_source(owner, seeded, reference_data):
    names = {s.name for s in reading.list_sources(owner)}
    cfg = get_current(owner, "reading").payload["items"]
    assert {i["source"] for i in cfg} <= names


def test_staff_visible_usage_never_names_a_legal_or_religious_text(
    owner, seeded, reference_data, make_resident
):
    rid = make_resident()
    reading.read_item(owner, rid, "psalm-23", NOW)
    reading.read_item(owner, rid, "bill-of-rights-selected", NOW)
    reading.read_item(owner, rid, "tortoise-hare", NOW)
    logged = sorted(
        owner.execute(select(ReadingLog.item_id).where(ReadingLog.resident_id == rid)).scalars()
    )
    assert logged == ["baseline", "baseline", "tortoise-hare"]


def test_progress_only_moves_forward_and_replays_are_harmless(
    owner, seeded, reference_data, make_resident
):
    rid = make_resident()
    t = "bill-of-rights-selected"
    assert reading.save_progress(owner, rid, t, 1, NOW)["page"] == 1
    assert reading.save_progress(owner, rid, t, 0, NOW)["page"] == 1  # an old queued event
    assert reading.save_progress(owner, rid, t, 99, NOW)["page"] == 2  # clamped to the last page
    assert reading.read_item(owner, rid, t, NOW)["page"] == 2
    assert reading.read_item(owner, rid, t, NOW)["completed"]
    assert listing(owner, rid, NOW)[t]["completed"]


def test_progress_is_refused_when_the_text_is_locked(
    owner, seeded, reference_data, make_resident, make_staff
):
    rid = make_resident()
    later = lock_everything(owner, rid, make_staff)
    with pytest.raises(reading.ReadingDenied):
        reading.save_progress(owner, rid, "tortoise-hare", 0, later)
    assert reading.save_progress(owner, rid, "psalm-23", 1, later)["page"] == 1


def test_bookmarks_toggle_idempotently_and_stay_inside_the_text(
    owner, seeded, reference_data, make_resident
):
    rid, t = make_resident(), "bill-of-rights-selected"
    assert reading.set_bookmark(owner, rid, t, 2, True, NOW)["bookmarks"] == [2]
    assert reading.set_bookmark(owner, rid, t, 2, True, NOW)["bookmarks"] == [2]
    assert reading.set_bookmark(owner, rid, t, 0, True, NOW)["bookmarks"] == [0, 2]
    assert reading.read_item(owner, rid, t, NOW)["bookmarks"] == [0, 2]
    assert listing(owner, rid, NOW)[t]["bookmarks"] == 2
    assert reading.set_bookmark(owner, rid, t, 2, False, NOW)["bookmarks"] == [0]
    assert reading.set_bookmark(owner, rid, t, 2, False, NOW)["bookmarks"] == [0]
    for bad in (-1, 3):
        with pytest.raises(reading.ReadingDenied) as e:
            reading.set_bookmark(owner, rid, t, bad, True, NOW)
        assert e.value.code == "BAD_PAGE"


def test_one_residents_bookmarks_and_progress_are_not_anothers(
    owner, seeded, reference_data, make_resident
):
    a, b, t = make_resident(), make_resident(), "psalm-23"
    reading.set_bookmark(owner, a, t, 1, True, NOW)
    reading.save_progress(owner, a, t, 2, NOW)
    assert reading.read_item(owner, b, t, NOW)["bookmarks"] == []
    assert reading.read_item(owner, b, t, NOW)["page"] == 0


def points_for(owner, rid):
    return list(
        owner.execute(
            select(PointEvent).where(
                PointEvent.resident_id == rid, PointEvent.kind == "book_completed"
            )
        ).scalars()
    )


def test_finishing_a_book_gives_no_points_by_default(owner, seeded, reference_data, make_resident):
    rid = make_resident()
    assert reading.save_progress(owner, rid, "psalm-23", 2, NOW)["points_awarded"] == 0
    assert points_for(owner, rid) == []  # a zero-point event would still be noise in the record


def set_book_points(owner, points):
    payload = get_current(owner, "points").payload
    payload["events"]["book_completed"]["points"] = points
    set_config(owner, SYSTEM, "points", payload, "test: reward reading")


def test_when_configured_a_book_pays_once_and_the_weekly_cap_holds(
    owner, seeded, reference_data, make_resident
):
    set_book_points(owner, 5)
    rid = make_resident()
    assert reading.save_progress(owner, rid, "psalm-23", 2, NOW)["points_awarded"] == 5
    assert reading.save_progress(owner, rid, "psalm-23", 2, NOW)["points_awarded"] == 0  # once
    for item in ("dhammapada-twin-verses", "bill-of-rights-selected"):
        reading.save_progress(owner, rid, item, 5, NOW)
    reading.save_progress(owner, rid, "tortoise-hare", 0, NOW)  # one-page text
    reading.save_progress(owner, rid, "lion-mouse", 0, NOW)
    assert len(points_for(owner, rid)) == 3  # max_per_week: the rest finish but earn nothing
    assert reading.read_item(owner, rid, "lion-mouse", NOW)["completed"]


def test_the_config_change_that_sets_book_points_is_audit_logged(owner, seeded):
    set_book_points(owner, 5)
    assert owner.execute(select(AuditLog).where(AuditLog.action.like("config%"))).first()


# ---------------- over HTTP ----------------
def dh(token):
    return {"X-Device-Token": token}


@pytest.mark.usefixtures("committed_config", "committed_reference")
def test_reader_routes_validate_input_and_refuse_locked_or_unknown_texts(client, kiosk):
    rid, token, _ = kiosk()
    page = client.get("/device/reading/psalm-23", headers=dh(token)).json()
    assert len(page["pages"]) == 3 and page["page"] == 0 and page["bookmarks"] == []
    saved = client.put("/device/reading/psalm-23/progress", json={"page": 1}, headers=dh(token))
    assert saved.status_code == 200 and saved.json()["page"] == 1
    assert client.get("/device/reading/psalm-23", headers=dh(token)).json()["page"] == 1
    mark = client.put("/device/reading/psalm-23/bookmarks/2", json={"on": True}, headers=dh(token))
    assert mark.json() == {"bookmarks": [2]}
    for bad in (
        client.put("/device/reading/psalm-23/progress", json={"page": -1}, headers=dh(token)),
        client.put("/device/reading/psalm-23/progress", json={"page": "x"}, headers=dh(token)),
        client.put("/device/reading/psalm-23/bookmarks/2", json={}, headers=dh(token)),
    ):
        assert bad.status_code == 422
    out_of_range = client.put(
        "/device/reading/psalm-23/bookmarks/9", json={"on": True}, headers=dh(token)
    )
    assert out_of_range.status_code == 409
    nope = client.put("/device/reading/nope/progress", json={"page": 0}, headers=dh(token))
    assert nope.status_code == 404
    locked = client.put("/device/reading/preamble/progress", json={"page": 0}, headers=dh(token))
    assert locked.status_code == 409 and locked.json()["detail"]["code"] == "FEATURE_LOCKED"
    assert client.put("/device/reading/psalm-23/progress", json={"page": 0}).status_code == 401


@pytest.mark.usefixtures("committed_config", "committed_reference")
def test_staff_cannot_switch_off_the_protected_source(client, owner_engine):
    import uuid

    from sqlalchemy.orm import Session

    from isd.auth import make_token
    from isd.models import Staff

    with Session(owner_engine) as s, s.begin():
        st = Staff(username=f"admin_{uuid.uuid4().hex[:8]}", role="admin", password_hash="x")
        s.add(st)
        s.flush()
        headers = {"Authorization": f"Bearer {make_token(st.id)}"}
    sources = client.get("/staff/content-sources", headers=headers).json()
    protected = next(x for x in sources if x["protected"])
    r = client.post(
        f"/staff/content-sources/{protected['id']}/active", json={"active": False}, headers=headers
    )
    assert r.status_code == 409 and "protected" in r.json()["detail"]
