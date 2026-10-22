"""Phase 11: video. Attorney video is never recorded; a covered camera ends the call and keeps
no picture; booked minutes come out of the weekly allowance."""

from datetime import timedelta

import pytest
from sqlalchemy import select, text

from isd.engine.calls import CallDenied
from isd.interfaces.telephony import PrivilegedCommunicationError
from isd.interfaces.video import VideoService
from isd.mocks.video import MockVideoProvider
from isd.models import CallRecord, Contact, Sanction, VideoBooking
from isd.services import calls, sanctions, video_bookings
from isd.services.audit import SYSTEM
from isd.services.config_store import get_current, set_config
from isd.services.entitlement_service import get_entitlements
from tests.conftest import NOW
from tests.test_phase7_services import give

TIER_6 = 1000  # 30 video minutes a week


@pytest.fixture
def vid():
    provider = MockVideoProvider()
    return VideoService(provider), provider


def contact_for(owner, rid, kind="family", phone="555-0111"):
    c = Contact(resident_id=rid, name="Synthetic Contact", type=kind, phone_ref=phone)
    owner.add(c)
    owner.flush()
    return c


def configure(owner, **changes):
    payload = dict(get_current(owner, "compliance").payload)
    payload.update(changes)
    set_config(owner, SYSTEM, "compliance", payload, "test: video settings")


MONDAY = NOW  # 2026-03-02 is a Monday


# ---------------- recording behind the interface ----------------
def test_monitored_video_is_recorded_only_when_the_operator_enables_it(
    owner, seeded, make_resident, vid
):
    service, provider = vid
    rid = make_resident()
    give(owner, rid, TIER_6)
    c = contact_for(owner, rid)
    off = calls.start_call(owner, rid, c.id, NOW, medium="video", video=service)
    assert off.monitored and not off.privileged
    done = calls.end_call(owner, rid, off.id, NOW + timedelta(minutes=2), video=service)
    assert done.monitor_ref is None  # default: nothing is recorded
    configure(owner, video_recording_enabled=True)
    on = calls.start_call(owner, rid, c.id, NOW + timedelta(hours=1), medium="video", video=service)
    done = calls.end_call(owner, rid, on.id, NOW + timedelta(hours=1, minutes=1), video=service)
    assert done.monitor_ref and done.monitor_ref.startswith("rec-")


def test_attorney_video_is_unmetered_and_never_recorded_even_when_recording_is_on(
    owner, seeded, make_resident, vid
):
    service, provider = vid
    rid = make_resident()
    give(owner, rid, TIER_6)
    configure(owner, video_recording_enabled=True)
    att = contact_for(owner, rid, "attorney", "555-0112")
    v = calls.start_call(owner, rid, att.id, NOW, medium="video", video=service)
    assert v.privileged and not v.monitored and v.max_seconds == 3600
    done = calls.end_call(owner, rid, v.id, NOW + timedelta(minutes=45), video=service)
    assert done.monitor_ref is None
    assert all(s["recording"] is None for s in provider.sessions.values())
    # a regular call is still metered at 30 minutes, since attorney minutes did not count
    fam = contact_for(owner, rid, phone="555-0113")
    r = calls.start_call(
        owner, rid, fam.id, NOW + timedelta(hours=2), medium="video", video=service
    )
    assert r.max_seconds == 30 * 60


def test_a_provider_that_records_attorney_video_is_caught_and_the_call_ends(
    owner, seeded, make_resident
):
    provider = MockVideoProvider(ignore_no_record=True)
    rid = make_resident()
    give(owner, rid, TIER_6)
    att = contact_for(owner, rid, "attorney", "555-0114")
    with pytest.raises(PrivilegedCommunicationError):
        calls.start_call(owner, rid, att.id, NOW, medium="video", video=VideoService(provider))
    assert all(s["ended"] for s in provider.sessions.values())
    assert owner.execute(select(CallRecord).where(CallRecord.resident_id == rid)).first() is None


def test_attorney_video_follows_the_video_lock_but_the_phone_stays_open(
    owner, seeded, make_resident, make_staff, vid
):
    service, _ = vid
    rid = make_resident()
    give(owner, rid, TIER_6)
    att = contact_for(owner, rid, "attorney", "555-0115")
    fam = contact_for(owner, rid, phone="555-0116")
    call = calls.start_call(owner, rid, fam.id, NOW, medium="video", video=service)
    s = calls.report_video_tamper(
        owner, rid, call.id, NOW + timedelta(minutes=1), "dark", video=service
    )
    sanctions.confirm_sanction(owner, make_staff("supervisor"), s.id, NOW + timedelta(minutes=2))
    later = NOW + timedelta(hours=1)
    with pytest.raises(CallDenied) as e:
        calls.start_call(owner, rid, att.id, later, medium="video", video=service)
    assert e.value.code == "FEATURE_LOCKED"
    phone = calls.start_call(owner, rid, att.id, later, medium="voice")
    assert phone.privileged  # attorney access by phone is baseline and never locks


# ---------------- tamper (invariant 14) ----------------
def test_tamper_ends_the_call_and_the_database_has_nowhere_to_keep_a_picture(
    owner, seeded, make_resident, vid
):
    service, _ = vid
    rid = make_resident()
    give(owner, rid, TIER_6)
    c = contact_for(owner, rid)
    v = calls.start_call(owner, rid, c.id, NOW, medium="video", video=service)
    s = calls.report_video_tamper(
        owner, rid, v.id, NOW + timedelta(seconds=40), "flat", video=service
    )
    assert (s.infraction_code, s.status, s.issued_by) == ("DEVICE_TAMPER", "pending", None)
    call = owner.get(CallRecord, v.id)
    assert call.status == "completed" and call.duration_seconds == 40
    binary = owner.execute(
        text(
            "SELECT table_name, column_name FROM information_schema.columns"
            " WHERE table_schema = 'public' AND data_type IN ('bytea', 'oid')"
        )
    ).all()
    assert binary == []  # no column anywhere can hold frames or any other binary data
    assert get_entitlements(owner, rid, NOW).allowed("video")  # until a supervisor confirms


def test_tamper_needs_an_active_call_a_known_signal_and_your_own_call(
    owner, seeded, make_resident, vid
):
    service, _ = vid
    rid, other = make_resident(), make_resident()
    give(owner, rid, TIER_6)
    c = contact_for(owner, rid)
    v = calls.start_call(owner, rid, c.id, NOW, medium="video", video=service)
    with pytest.raises(CallDenied) as e:
        calls.report_video_tamper(owner, rid, v.id, NOW, "sparkly", video=service)
    assert e.value.code == "BAD_SIGNAL"
    with pytest.raises(CallDenied) as e:
        calls.report_video_tamper(owner, other, v.id, NOW, "dark", video=service)
    assert e.value.code == "NOT_FOUND"
    calls.end_call(owner, rid, v.id, NOW + timedelta(minutes=1), video=service)
    with pytest.raises(CallDenied) as e:
        calls.report_video_tamper(
            owner, rid, v.id, NOW + timedelta(minutes=2), "dark", video=service
        )
    assert e.value.code == "NOT_ACTIVE"
    assert owner.execute(select(Sanction).where(Sanction.resident_id == rid)).first() is None


# ---------------- retention ----------------
def test_recordings_past_the_retention_period_are_deleted_and_the_rest_kept(
    owner, seeded, make_resident, vid
):
    service, provider = vid
    rid = make_resident()
    give(owner, rid, TIER_6)
    configure(owner, video_recording_enabled=True)
    c = contact_for(owner, rid)
    old = calls.start_call(owner, rid, c.id, NOW, medium="video", video=service)
    calls.end_call(owner, rid, old.id, NOW + timedelta(minutes=1), video=service)
    new = calls.start_call(
        owner, rid, c.id, NOW + timedelta(days=20), medium="video", video=service
    )
    calls.end_call(owner, rid, new.id, NOW + timedelta(days=20, minutes=1), video=service)
    later = NOW + timedelta(days=40)
    assert calls.purge_expired_recordings(owner, later, service) == 0  # retention not set: keep
    configure(owner, recording_retention_days=30)
    assert calls.purge_expired_recordings(owner, later, service) == 1
    assert owner.get(CallRecord, old.id).monitor_ref is None
    assert owner.get(CallRecord, old.id).recording_purged_at == later
    assert owner.get(CallRecord, new.id).monitor_ref is not None
    assert provider.deleted == [old.provider_ref]
    assert calls.purge_expired_recordings(owner, later, service) == 0  # repeat-safe


# ---------------- scheduled calls ----------------
def slot(day=1, hour=10, minute=0):
    return MONDAY.replace(hour=hour, minute=minute) + timedelta(days=day - 0)


def test_booking_reserves_minutes_and_refuses_what_the_week_cannot_hold(
    owner, seeded, make_resident
):
    rid = make_resident()
    give(owner, rid, TIER_6)  # 30 minutes a week
    c = contact_for(owner, rid)
    b = video_bookings.book(owner, rid, c.id, slot(1), 15, NOW)
    assert b.status == "scheduled"
    video_bookings.book(owner, rid, c.id, slot(2), 15, NOW)
    with pytest.raises(CallDenied) as e:
        video_bookings.book(owner, rid, c.id, slot(3), 15, NOW)  # same week: only 30 minutes
    assert e.value.code == "LIMIT_REACHED"
    video_bookings.cancel(owner, rid, b.id, NOW)
    video_bookings.book(owner, rid, c.id, slot(3), 15, NOW)  # the cancelled minutes came back


def test_slot_rules(owner, seeded, make_resident):
    rid = make_resident()
    give(owner, rid, TIER_6)
    c = contact_for(owner, rid)
    for starts, minutes in (
        (slot(1, minute=7), 15),  # off the 15-minute grid
        (slot(1), 20),  # not a whole number of slots
        (slot(1), 45),  # longer than the longest booking
        (NOW - timedelta(hours=1), 15),  # the past
        (NOW + timedelta(days=9), 15),  # too far ahead
    ):
        with pytest.raises(CallDenied) as e:
            video_bookings.book(owner, rid, c.id, starts, minutes, NOW)
        assert e.value.code == "BAD_SLOT"
    video_bookings.book(owner, rid, c.id, slot(1), 30, NOW)
    with pytest.raises(CallDenied) as e:
        video_bookings.book(owner, rid, c.id, slot(1, minute=15), 15, NOW)  # overlaps
    assert e.value.code == "SLOT_TAKEN"


def test_booking_is_locked_with_video_and_for_blocked_or_other_peoples_contacts(
    owner, seeded, make_resident
):
    rid, other = make_resident(), make_resident()
    c = contact_for(owner, rid)
    with pytest.raises(CallDenied) as e:  # tier 1: no video
        video_bookings.book(owner, rid, c.id, slot(1), 15, NOW)
    assert e.value.code == "FEATURE_LOCKED"
    give(owner, rid, TIER_6)
    give(owner, other, TIER_6)
    with pytest.raises(CallDenied) as e:
        video_bookings.book(owner, other, c.id, slot(1), 15, NOW)
    assert e.value.code == "CONTACT_UNAVAILABLE"
    c.blocked = True
    with pytest.raises(CallDenied):
        video_bookings.book(owner, rid, c.id, slot(1), 15, NOW)


def test_an_ad_hoc_call_cannot_spend_minutes_that_are_booked(owner, seeded, make_resident, vid):
    service, _ = vid
    rid = make_resident()
    give(owner, rid, TIER_6)
    c = contact_for(owner, rid)
    video_bookings.book(owner, rid, c.id, slot(1), 15, NOW)
    adhoc = calls.start_call(owner, rid, c.id, NOW, medium="video", video=service)
    assert adhoc.max_seconds == 15 * 60  # 30 a week, 15 of them promised to the booking


def test_a_booked_call_starts_in_its_window_and_is_capped_to_its_slot(
    owner, seeded, make_resident, vid
):
    service, _ = vid
    rid = make_resident()
    give(owner, rid, TIER_6)
    c = contact_for(owner, rid)
    b = video_bookings.book(owner, rid, c.id, slot(1), 15, NOW)
    with pytest.raises(CallDenied) as e:
        video_bookings.start_booked(owner, rid, b.id, b.starts_at - timedelta(minutes=30))
    assert e.value.code == "TOO_EARLY"
    started = video_bookings.start_booked(owner, rid, b.id, b.starts_at - timedelta(minutes=4))
    assert started.medium == "video" and started.max_seconds == 15 * 60
    assert owner.get(VideoBooking, b.id).status == "started"
    assert owner.get(VideoBooking, b.id).call_id == started.id
    with pytest.raises(CallDenied) as e:
        video_bookings.start_booked(owner, rid, b.id, b.starts_at)
    assert e.value.code == "NOT_SCHEDULED"


def test_a_slot_nobody_used_is_missed_and_stops_holding_minutes(owner, seeded, make_resident):
    rid = make_resident()
    give(owner, rid, TIER_6)
    c = contact_for(owner, rid)
    b = video_bookings.book(owner, rid, c.id, slot(1), 30, NOW)
    after = b.starts_at + timedelta(minutes=45)
    assert video_bookings.upcoming(owner, rid, after) == []
    assert owner.get(VideoBooking, b.id).status == "missed"
    with pytest.raises(CallDenied) as e:
        video_bookings.start_booked(owner, rid, b.id, after)
    assert e.value.code == "NOT_SCHEDULED"


def test_a_no_contact_order_cancels_booked_calls_with_that_person(
    owner, seeded, make_resident, make_staff
):
    from isd.services import contacts

    rid = make_resident()
    give(owner, rid, TIER_6)
    c = contact_for(owner, rid)
    b = video_bookings.book(owner, rid, c.id, slot(1), 15, NOW)
    contacts.set_blocked(owner, make_staff("supervisor"), c.id, True, "court order", NOW)
    assert owner.get(VideoBooking, b.id).status == "cancelled"


# ---------------- over HTTP ----------------
def dh(token):
    return {"X-Device-Token": token}


@pytest.mark.usefixtures("committed_config", "committed_reference")
def test_video_routes_end_to_end(client, kiosk, owner_engine):
    from sqlalchemy.orm import Session

    from isd.services import points

    rid, token, _ = kiosk()
    with Session(owner_engine) as s, s.begin():
        points.record_points(
            s, SYSTEM, rid, "seed_adjustment", TIER_6, "system", NOW - timedelta(days=1)
        )
        points.evaluate_tier(s, rid, NOW)
        family = contact_for(s, rid, phone="555-0121").id
        attorney = contact_for(s, rid, "attorney", "555-0122").id
    dev = dh(token)

    v = client.post("/device/video-calls", json={"contact_id": family}, headers=dev)
    assert v.status_code == 201
    body = v.json()
    assert (
        body["medium"] == "video"
        and body["monitored"]
        and body["connection"] == {"mode": "loopback"}
    )
    call = body["call_id"]
    # the device may say only that the camera is covered, and for how long; never an image
    for bad in (
        {"signal": "dark", "covered_ms": 3000, "frame": "aGVsbG8="},
        {"signal": "dark"},
        {"signal": "dark", "covered_ms": -1},
        {"signal": "sparkly", "covered_ms": 3000},
    ):
        r = client.post(f"/device/video-calls/{call}/tamper", json=bad, headers=dev)
        assert r.status_code in (409, 422)
    ok = client.post(
        f"/device/video-calls/{call}/tamper",
        json={"signal": "dark", "covered_ms": 3000},
        headers=dev,
    )
    assert ok.status_code == 200 and ok.json()["status"] == "pending"
    ended = client.post(f"/device/calls/{call}/end", headers=dev).json()
    assert ended["status"] == "completed"  # the tamper report already ended it

    # attorney video works, is flagged private, and is never offered a recording
    att = client.post("/device/video-calls", json={"contact_id": attorney}, headers=dev)
    assert att.status_code == 201 and att.json()["privileged"] and not att.json()["monitored"]
    client.post(f"/device/calls/{att.json()['call_id']}/end", headers=dev)

    # booking, in real time (the routes use the server clock)
    from datetime import UTC, datetime

    start = datetime.now(UTC).replace(hour=10, minute=0, second=0, microsecond=0) + timedelta(
        days=2
    )
    payload = {"contact_id": family, "starts_at": start.isoformat(), "minutes": 15}
    made = client.post("/device/video-bookings", json=payload, headers=dev)
    assert made.status_code == 201 and made.json()["status"] == "scheduled"
    booking = made.json()["id"]
    assert [b["id"] for b in client.get("/device/video-bookings", headers=dev).json()] == [booking]
    clash = client.post("/device/video-bookings", json=payload, headers=dev)
    assert clash.status_code == 409 and clash.json()["detail"]["code"] == "SLOT_TAKEN"
    early = client.post(f"/device/video-bookings/{booking}/start", headers=dev)
    assert early.status_code == 409 and early.json()["detail"]["code"] == "TOO_EARLY"
    assert client.post(f"/device/video-bookings/{booking}/cancel", headers=dev).json()[
        "status"
    ] == ("cancelled")
    assert client.get("/device/video-bookings", headers=dev).json() == []

    bad_time = {**payload, "starts_at": "not a time"}
    assert client.post("/device/video-bookings", json=bad_time, headers=dev).status_code == 422
    extra = {**payload, "note": "x"}
    assert client.post("/device/video-bookings", json=extra, headers=dev).status_code == 422
    missing = {"contact_id": family}
    assert client.post("/device/video-bookings", json=missing, headers=dev).status_code == 422
    assert client.post("/device/video-bookings/999999/start", headers=dev).status_code == 404
    assert client.post("/device/video-calls", json={"contact_id": family}).status_code == 401
