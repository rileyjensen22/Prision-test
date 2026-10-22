"""Release countdown, checklist, resources directory and the device view of them."""

from datetime import date, timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from isd.models import AuditLog, ReentryEvent, Resident
from isd.services import reentry
from isd.services.reentry import ReentryError
from isd.services.resident_view import build_resident_view
from tests.conftest import NOW


@pytest.fixture
def rid(owner, make_resident, seeded):
    return make_resident()


def test_no_release_date_means_no_countdown_in_the_view(owner, rid):
    assert build_resident_view(owner, rid, NOW).reentry is None


def test_countdown_appears_in_the_resident_view_and_counts_down(owner, rid, make_staff):
    reentry.set_release_date(
        owner, make_staff("supervisor"), rid, NOW.date() + timedelta(days=45), "plan", NOW
    )
    view = build_resident_view(owner, rid, NOW)
    assert view.reentry["days_left"] == 45 and view.reentry["weeks_left"] == 6
    later = build_resident_view(owner, rid, NOW + timedelta(days=10))
    assert later.reentry["days_left"] == 35


def test_release_date_changes_need_a_reason_and_are_audited(owner, rid, make_staff):
    actor = make_staff("supervisor")
    with pytest.raises(ReentryError, match="reason"):
        reentry.set_release_date(owner, actor, rid, NOW.date() + timedelta(days=5), " ", NOW)
    with pytest.raises(ReentryError):
        reentry.set_release_date(owner, actor, rid, date(2020, 1, 1), "plan", NOW)
    reentry.set_release_date(owner, actor, rid, NOW.date() + timedelta(days=5), "plan", NOW)
    reentry.set_release_date(owner, actor, rid, None, "date withdrawn", NOW)
    entries = (
        owner.execute(
            select(AuditLog).where(AuditLog.action == "release_date_set").order_by(AuditLog.seq)
        )
        .scalars()
        .all()
    )
    assert [e.payload["to"] for e in entries] == [
        (NOW.date() + timedelta(days=5)).isoformat(),
        None,
    ]
    assert entries[1].payload["from"] is not None
    assert owner.get(Resident, rid).release_date is None


def test_checklist_history_is_append_only_and_latest_wins(owner, rid, make_staff):
    actor = make_staff("officer")
    reentry.record_item(owner, actor, rid, "HOUSING", "in_progress", "called a shelter", NOW)
    reentry.record_item(owner, actor, rid, "HOUSING", "done", None, NOW + timedelta(hours=1))
    assert reentry.statuses(owner, rid)["HOUSING"] == "done"
    assert reentry.statuses(owner, rid)["ID_DOCUMENTS"] == "todo"
    for sql in ("UPDATE reentry_events SET status = 'todo'", "DELETE FROM reentry_events"):
        with pytest.raises(DBAPIError):
            with owner.begin_nested():
                owner.execute(text(sql))
    log = " ".join(str(a.payload) for a in owner.execute(select(AuditLog)).scalars())
    assert "called a shelter" not in log  # the note is kept out of the audit log


@pytest.mark.parametrize(
    ("item", "status", "code"),
    [("NOPE", "done", "UNKNOWN_ITEM"), ("HOUSING", "finished", "BAD_STATUS")],
)
def test_bad_items_are_refused(owner, rid, make_staff, item, status, code):
    with pytest.raises(ReentryError) as e:
        reentry.record_item(owner, make_staff("officer"), rid, item, status, None, NOW)
    assert e.value.code == code
    assert owner.execute(select(ReentryEvent)).first() is None


def test_device_view_has_checklist_courses_and_resources(owner, rid, make_staff):
    reentry.record_item(owner, make_staff("officer"), rid, "ID_DOCUMENTS", "done", None, NOW)
    view = reentry.resident_view(owner, rid, NOW)
    assert view["progress"] == {"done": 1, "resolved": 1, "total": 5}
    assert {c["code"] for c in view["courses"]} == {"JOBS101", "CREDIT201", "REENTRY301"}
    assert {r["code"] for r in view["resources"]} >= {"SAMPLE_HOUSING"}
    assert all(r["phone"].startswith("555-01") for r in view["resources"])  # synthetic only
    assert view["countdown"] is None


@pytest.mark.usefixtures("committed_config")
def test_reentry_over_http_roles_and_device(client, kiosk, staff_tokens):
    rid, token, _ = kiosk()
    path = f"/staff/residents/{rid}"
    future = (date.today() + timedelta(days=30)).isoformat()
    body = {"release_date": future, "reason": "sentence end"}
    assert (
        client.put(f"{path}/release-date", json=body, headers=staff_tokens["officer"]).status_code
        == 403
    )
    assert (
        client.put(
            f"{path}/release-date", json=body, headers=staff_tokens["supervisor"]
        ).status_code
        == 200
    )
    item = {"item_code": "HOUSING", "status": "done"}
    assert (
        client.post(f"{path}/reentry-items", json=item, headers=staff_tokens["auditor"]).status_code
        == 403
    )
    assert (
        client.post(f"{path}/reentry-items", json=item, headers=staff_tokens["officer"]).status_code
        == 201
    )
    staff = client.get(f"{path}/reentry", headers=staff_tokens["auditor"]).json()
    assert staff["release_date"] == future
    assert [i for i in staff["checklist"] if i["code"] == "HOUSING"][0]["status"] == "done"

    device = client.get("/device/reentry", headers={"X-Device-Token": token}).json()
    assert device["countdown"]["days_left"] == 30
    assert client.get("/device/reentry").status_code == 401
    # the resident cannot change any of it
    assert client.post(
        "/device/reentry", headers={"X-Device-Token": token}, json=item
    ).status_code in (404, 405)
    view = client.get("/device/view", headers={"X-Device-Token": token}).json()
    assert view["reentry"]["days_left"] == 30
