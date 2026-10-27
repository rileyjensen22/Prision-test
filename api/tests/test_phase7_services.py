from datetime import timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from isd.engine.calls import CallDenied
from isd.interfaces.facility import FacilityEventIn
from isd.interfaces.messaging import MessagingService
from isd.interfaces.telephony import PrivilegedCommunicationError
from isd.mocks.messaging import MockMessagingProvider
from isd.models import (
    AuditLog,
    CallRecord,
    Cell,
    ChessGame,
    ChessMove,
    Contact,
    Device,
    DeviceAssignment,
    Message,
    OutOfCellLog,
    Resident,
    Sanction,
)
from isd.services import (
    calls,
    facility,
    out_of_cell,
    points,
    reading,
    rec,
    sanctions,
    texting,
    timeline,
    welfare,
)
from isd.services.audit import SYSTEM, Actor, verify_chain
from isd.services.entitlement_service import get_entitlements
from tests.conftest import NOW


def give(owner, rid, n):
    points.record_points(
        owner, SYSTEM, rid, "seed_adjustment", n, "system", NOW - timedelta(days=1)
    )
    points.evaluate_tier(owner, rid, NOW)


@pytest.fixture
def add_contact(owner):
    def _add(rid, type_="family", blocked=False, name="Synthetic Contact", phone="555-0100"):
        c = Contact(resident_id=rid, name=name, type=type_, blocked=blocked, phone_ref=phone)
        owner.add(c)
        owner.flush()
        return c.id

    return _add


def assign(owner, rid, days_ago, cell="C"):
    c, d = Cell(code=f"{cell}-{rid}"), Device(code=f"D-{cell}-{rid}")
    owner.add_all([c, d])
    owner.flush()
    owner.add(
        DeviceAssignment(
            device_id=d.id,
            cell_id=c.id,
            resident_id=rid,
            assigned_at=NOW - timedelta(days=days_ago),
        )
    )
    owner.flush()
    return c.code


# ======================= out-of-cell log =======================
def test_out_of_cell_corrections_are_new_rows_and_latest_wins(owner, seeded, make_resident):
    rid = make_resident()
    staff = Actor(None, "officer")
    day = NOW.date() - timedelta(days=1)
    out_of_cell.record(owner, staff, rid, day, 30, "facility", NOW)
    out_of_cell.record(
        owner, staff, rid, day, 75, "facility", NOW + timedelta(hours=1)
    )  # correction
    assert out_of_cell.by_day(owner, rid, day, day) == {day: 75}
    assert (
        owner.execute(select(OutOfCellLog).where(OutOfCellLog.resident_id == rid))
        .scalars()
        .all()
        .__len__()
        == 2
    )
    for bad in (-1, 1441):
        with pytest.raises(ValueError):
            out_of_cell.record(owner, staff, rid, day, bad, "facility", NOW)
    with pytest.raises(ValueError):
        out_of_cell.record(owner, staff, rid, NOW.date() + timedelta(days=1), 60, "facility", NOW)
    assert verify_chain(owner).ok


def test_out_of_cell_log_is_append_only(owner_engine, owner, seeded, make_resident):
    from sqlalchemy.orm import Session

    with Session(owner_engine) as s, s.begin():
        r = Resident(code="R-OOC-APPEND", display_name="Synthetic")
        s.add(r)
        s.flush()
        s.add(
            OutOfCellLog(
                resident_id=r.id, day=NOW.date(), minutes=60, source="facility", created_at=NOW
            )
        )
        rid = r.id
    for stmt in (
        "UPDATE out_of_cell_log SET minutes = 999 WHERE resident_id = :r",
        "DELETE FROM out_of_cell_log WHERE resident_id = :r",
    ):
        with owner_engine.connect() as c, pytest.raises(DBAPIError, match="append-only"):
            c.execute(text(stmt), {"r": rid})


# ======================= welfare =======================
def add_calls(owner, rid, contact_id, days_ago_list, per_day=1):
    for d in days_ago_list:
        for k in range(per_day):
            owner.add(
                CallRecord(
                    resident_id=rid,
                    contact_id=contact_id,
                    contact_type="family",
                    privileged=False,
                    monitored=True,
                    provider_ref="x",
                    started_at=NOW - timedelta(days=d, hours=k),
                    ended_at=NOW - timedelta(days=d, hours=k) + timedelta(minutes=5),
                    max_seconds=900,
                    duration_seconds=300,
                    status="completed",
                )
            )
    owner.flush()


def record_ooc(owner, rid, days=7, minutes=90):
    for d in range(days):
        out_of_cell.record(
            owner,
            Actor(None, "officer"),
            rid,
            NOW.date() - timedelta(days=d),
            minutes,
            "facility",
            NOW,
        )


def flag_types(owner, rid, tracked, now=NOW):
    return {f["type"] for f in welfare.resident_flags(owner, rid, tracked, now)}


def test_a_resident_who_goes_quiet_is_flagged_against_their_own_baseline(
    owner, seeded, make_resident, add_contact
):
    rid = make_resident()
    cid = add_contact(rid)
    add_calls(
        owner, rid, cid, range(8, 28), per_day=2
    )  # chatty for three weeks, silent for the last eight days
    record_ooc(owner, rid)
    types = flag_types(owner, rid, tracked=40)
    assert {
        "no_contact",
        "usage_drop",
    } <= types and "contact_drop" not in types  # no_contact already says it


def test_steady_residents_and_new_residents(owner, seeded, make_resident, add_contact):
    steady = make_resident()
    add_calls(owner, steady, add_contact(steady), range(0, 28))
    record_ooc(owner, steady)
    assert flag_types(owner, steady, tracked=60) == set()

    newcomer = make_resident()
    record_ooc(owner, newcomer)
    assert flag_types(owner, newcomer, tracked=3) == set()  # too new to judge
    assert flag_types(owner, newcomer, tracked=9) == {
        "no_contact"
    }  # but nine days of silence is flagged


def test_a_moderate_dip_is_not_a_flag(owner, seeded, make_resident, add_contact):
    rid = make_resident()
    cid = add_contact(rid)
    add_calls(owner, rid, cid, range(7, 28), per_day=4)
    add_calls(owner, rid, cid, range(0, 7), per_day=2)  # half as active, but still in touch
    record_ooc(owner, rid)
    assert flag_types(owner, rid, tracked=60) == set()


def test_out_of_cell_minimum_and_missing_records_are_flagged(
    owner, seeded, make_resident, add_contact
):
    rid = make_resident()
    add_calls(owner, rid, add_contact(rid), range(0, 28))
    day4 = NOW.date() - timedelta(days=4)
    out_of_cell.record(owner, Actor(None, "officer"), rid, day4, 20, "facility", NOW)
    flags = {f["type"]: f for f in welfare.resident_flags(owner, rid, 60, NOW)}
    assert flags["out_of_cell_below"]["detail"]["lowest"] == 20
    assert flags["out_of_cell_below"]["detail"]["minimum"] == 60  # the configured minimum
    assert flags["out_of_cell_unrecorded"]["detail"] == {
        "days": 4
    }  # nothing entered for the 4 days since
    # a correction is a new row; exactly the minimum is fine
    out_of_cell.record(
        owner, Actor(None, "officer"), rid, day4, 60, "facility", NOW + timedelta(hours=1)
    )
    types = flag_types(owner, rid, 60)
    assert "out_of_cell_below" not in types and "out_of_cell_unrecorded" in types


def test_acknowledging_a_flag_quiets_it_for_a_while_and_is_audited(
    owner, seeded, make_resident, add_contact, make_staff
):
    nurse = make_staff("officer")
    rid = make_resident()
    assign(owner, rid, 40)  # flags are tracked for residents with a device
    add_calls(owner, rid, add_contact(rid), range(8, 28))
    record_ooc(owner, rid)
    assert "no_contact" in flag_types(owner, rid, 40)
    welfare.acknowledge(
        owner,
        nurse,
        rid,
        "no_contact",
        "Spoke with the resident; they were unwell",
        NOW,
    )
    assert "no_contact" not in flag_types(owner, rid, 40)
    assert "no_contact" in flag_types(
        owner, rid, 44, NOW + timedelta(days=4)
    )  # the quiet period (3 days) is over
    with pytest.raises(ValueError):
        welfare.acknowledge(owner, nurse, rid, "no_contact", "x", NOW)
    with pytest.raises(ValueError):
        welfare.acknowledge(owner, nurse, rid, "made_up", "checked in on them", NOW)
    entry = (
        owner.execute(select(AuditLog).where(AuditLog.action == "welfare_ack")).scalars().first()
    )
    assert entry.payload["flag"] == "no_contact"


def test_all_flags_skips_residents_without_a_device(owner, seeded, make_resident):
    rid = make_resident()
    assert all(f["resident_id"] != rid for f in welfare.all_flags(owner, NOW))
    assign(owner, rid, 40)
    assert any(f["resident_id"] == rid for f in welfare.all_flags(owner, NOW))


# ======================= timeline =======================
def test_timeline_is_metadata_only_and_every_look_is_logged(
    owner, seeded, make_resident, add_contact, make_staff
):
    rid = make_resident()
    give(owner, rid, 450)  # tier 4: texting
    attorney = add_contact(rid, "attorney", name="Counsel Zebadee", phone="555-0188")
    family = add_contact(rid, "family", name="Aunt Quillfeather", phone="555-0177")
    texting.send_text(owner, rid, family, "I miss you all, see you at Christmas", NOW)
    texting.send_text(owner, rid, attorney, "Please file the motion about the evidence", NOW)
    c = calls.start_call(owner, rid, attorney, NOW)
    calls.end_call(owner, rid, c.id, NOW + timedelta(minutes=12))

    sup = make_staff("supervisor")
    events = timeline.timeline(
        owner, sup, rid, "welfare review requested", NOW + timedelta(hours=1)
    )
    blob = str(events)
    for secret in (
        "Counsel Zebadee",
        "Aunt Quillfeather",
        "555-0188",
        "555-0177",
        "Christmas",
        "motion",
        "evidence",
    ):
        assert secret not in blob
    call = next(e for e in events if e["kind"] == "call")
    assert call["detail"]["privileged"] is True and call["detail"]["seconds"] == 720
    assert call["detail"]["contact_type"] == "attorney"
    assert {e["kind"] for e in events} >= {"call", "text message", "points"}
    entry = (
        owner.execute(select(AuditLog).where(AuditLog.action == "monitoring_access"))
        .scalars()
        .all()[-1]
    )
    assert (entry.reason_code, entry.actor_id) == ("TIMELINE_VIEW", sup.id)
    assert entry.payload["reason"] == "welfare review requested" and entry.payload[
        "entries"
    ] == len(events)


def test_timeline_roles_and_reason(owner, seeded, make_resident, make_staff):
    rid = make_resident()
    with pytest.raises(timeline.TimelineDenied) as e:
        timeline.timeline(owner, make_staff("officer"), rid, "just curious here", NOW)
    assert e.value.code == "ROLE_NOT_PERMITTED"
    with pytest.raises(timeline.TimelineDenied) as e:
        timeline.timeline(owner, make_staff("supervisor"), rid, "no", NOW)
    assert e.value.code == "REASON_REQUIRED"
    timeline.timeline(owner, make_staff("auditor"), rid, "annual compliance audit", NOW)


# ======================= facility events =======================
def test_camera_obstruction_makes_a_pending_sanction_never_an_active_one(
    owner, seeded, make_resident, make_staff
):
    rid = make_resident()
    cell = assign(owner, rid, 1)
    ev = FacilityEventIn("evt-cam-0001", "camera_obstruction", {"cell": cell})
    result = facility.ingest(owner, ev, NOW)
    assert result.startswith("sanction:") and result.endswith(":pending")
    s = owner.execute(select(Sanction).where(Sanction.resident_id == rid)).scalars().one()
    assert (s.infraction_code, s.status, s.issued_by, s.evidence_type, s.evidence_ref) == (
        "CAM_BLOCK",
        "pending",
        None,
        "system_event",
        "evt-cam-0001",
    )
    assert get_entitlements(owner, rid, NOW).allowed(
        "calls"
    )  # nothing locks until a supervisor confirms
    assert facility.ingest(owner, ev, NOW) == result  # same event again: no second sanction
    assert (
        len(owner.execute(select(Sanction).where(Sanction.resident_id == rid)).scalars().all()) == 1
    )
    sanctions.confirm_sanction(owner, make_staff("supervisor"), s.id, NOW)
    assert not get_entitlements(owner, rid, NOW).allowed("calls")


def test_facility_events_for_unknown_cells_and_types_are_ignored(owner, seeded):
    assert facility.ingest(
        owner, FacilityEventIn("evt-x-0001", "camera_obstruction", {"cell": "NOPE"}), NOW
    ).startswith("ignored")
    assert facility.ingest(owner, FacilityEventIn("evt-x-0002", "mystery", {}), NOW).startswith(
        "ignored"
    )


def test_out_of_cell_minutes_can_arrive_from_the_facility(owner, seeded, make_resident):
    rid = make_resident()
    code = owner.get(Resident, rid).code
    day = (NOW.date() - timedelta(days=1)).isoformat()
    r = facility.ingest(
        owner,
        FacilityEventIn(
            "evt-ooc-0001", "out_of_cell", {"resident_code": code, "day": day, "minutes": 95}
        ),
        NOW,
    )
    assert r == "out_of_cell:recorded"
    assert owner.execute(
        select(OutOfCellLog.source, OutOfCellLog.minutes).where(OutOfCellLog.resident_id == rid)
    ).one() == ("ingest", 95)


# ======================= video =======================
def test_video_has_its_own_weekly_allowance_and_never_counts_as_a_phone_call(
    owner, seeded, make_resident, add_contact
):
    rid = make_resident()
    give(owner, rid, 1000)  # tier 6: 30 video minutes per week
    cid = add_contact(rid)
    v = calls.start_call(owner, rid, cid, NOW, medium="video")
    assert v.medium == "video" and v.monitored and v.max_seconds == 30 * 60
    calls.end_call(owner, rid, v.id, NOW + timedelta(minutes=20))
    again = calls.start_call(owner, rid, cid, NOW + timedelta(minutes=21), medium="video")
    assert again.max_seconds == 10 * 60  # 20 of the week's 30 minutes are gone
    calls.end_call(owner, rid, again.id, NOW + timedelta(minutes=40))
    with pytest.raises(CallDenied) as e:
        calls.start_call(owner, rid, cid, NOW + timedelta(minutes=50), medium="video")
    assert e.value.code == "LIMIT_REACHED"
    assert (
        calls.start_call(owner, rid, cid, NOW + timedelta(minutes=50)).max_seconds == 45 * 60
    )  # voice minutes untouched


def test_video_is_locked_below_tier_6_and_not_offered_for_attorneys(
    owner, seeded, make_resident, add_contact
):
    rid = make_resident()
    cid, att = add_contact(rid), add_contact(rid, "attorney")
    with pytest.raises(CallDenied) as e:
        calls.start_call(owner, rid, cid, NOW, medium="video")
    assert e.value.code == "FEATURE_LOCKED"
    give(owner, rid, 1000)
    v = calls.start_call(owner, rid, att, NOW, medium="video")
    assert v.privileged and not v.monitored  # attorney video: unmetered, never recorded


def test_covering_the_camera_ends_the_call_and_raises_device_tamper_once(
    owner, seeded, make_resident, add_contact, make_staff
):
    rid = make_resident()
    give(owner, rid, 1000)
    v = calls.start_call(owner, rid, add_contact(rid), NOW, medium="video")
    s = calls.report_video_tamper(owner, rid, v.id, NOW + timedelta(minutes=3))
    assert (s.infraction_code, s.status, s.issued_by, s.evidence_ref) == (
        "DEVICE_TAMPER",
        "pending",
        None,
        f"video-call-{v.id}",
    )
    call = owner.get(CallRecord, v.id)
    assert call.status == "completed" and call.duration_seconds == 180
    assert (
        calls.report_video_tamper(owner, rid, v.id, NOW + timedelta(minutes=4)).id == s.id
    )  # not duplicated
    assert get_entitlements(owner, rid, NOW).allowed("video")  # still only a pending event
    sanctions.confirm_sanction(owner, make_staff("supervisor"), s.id, NOW + timedelta(minutes=5))
    ent = get_entitlements(owner, rid, NOW + timedelta(minutes=6))
    assert not ent.allowed("video") and ent.allowed("calls") and ent.allowed("attorney_calls")
    with pytest.raises(CallDenied):
        calls.report_video_tamper(owner, rid, 999999, NOW)


def test_tamper_is_refused_when_the_call_is_not_active(owner, seeded, make_resident, add_contact):
    """Invariant 14: tamper detection only runs during an active call."""
    rid = make_resident()
    give(owner, rid, 1000)
    v = calls.start_call(owner, rid, add_contact(rid), NOW, medium="video")
    calls.end_call(owner, rid, v.id, NOW + timedelta(minutes=1))
    with pytest.raises(CallDenied) as e:
        calls.report_video_tamper(owner, rid, v.id, NOW + timedelta(minutes=2))
    assert e.value.code == "NOT_ACTIVE"
    assert (
        owner.execute(select(Sanction).where(Sanction.evidence_ref == f"video-call-{v.id}")).first()
        is None
    )


# ======================= texting =======================
def test_texting_is_monitored_tier_gated_and_limited(owner, seeded, make_resident, add_contact):
    rid = make_resident()
    cid = add_contact(rid)
    with pytest.raises(texting.TextDenied) as e:
        texting.send_text(owner, rid, cid, "hello", NOW)
    assert e.value.code == "FEATURE_LOCKED"
    give(owner, rid, 450)  # tier 4: 10 a day
    m = texting.send_text(owner, rid, cid, "  hello there  ", NOW)
    assert m.monitored and not m.privileged and m.body == "hello there"
    assert [t.direction for t in texting.thread(owner, rid, cid)] == [
        "out",
        "in",
    ]  # plus the mock reply
    for i in range(9):
        texting.send_text(owner, rid, cid, f"message {i}", NOW)
    with pytest.raises(texting.TextDenied) as e:
        texting.send_text(owner, rid, cid, "one too many", NOW)
    assert e.value.code == "LIMIT_REACHED"
    texting.send_text(owner, rid, cid, "new day", NOW + timedelta(days=1))
    for bad in ("", "   ", "x" * 501):
        with pytest.raises(texting.TextDenied) as e:
            texting.send_text(owner, rid, cid, bad, NOW + timedelta(days=2))
        assert e.value.code == "BAD_MESSAGE"


def test_attorney_messages_are_never_stored_or_kept_by_the_provider(
    owner, seeded, make_resident, add_contact
):
    provider = MockMessagingProvider()
    svc = MessagingService(provider)
    rid = make_resident()
    give(owner, rid, 450)
    att = add_contact(rid, "attorney", blocked=True)  # a no-contact order never blocks an attorney
    m = texting.send_text(owner, rid, att, "Please bring the sealed documents", NOW, messaging=svc)
    assert m.privileged and not m.monitored and m.body is None
    assert all(
        copy is None for copy in provider.copies.values()
    )  # the provider was told not to keep it
    rows = owner.execute(select(Message).where(Message.resident_id == rid)).scalars().all()
    assert len(rows) == 1 and rows[0].body is None  # no reply row either
    assert "sealed" not in str(owner.execute(text("SELECT * FROM messages")).fetchall())


def test_a_provider_that_keeps_attorney_messages_is_stopped(
    owner, seeded, make_resident, add_contact
):
    svc = MessagingService(MockMessagingProvider(ignore_no_retain=True))
    rid = make_resident()
    give(owner, rid, 450)
    with pytest.raises(PrivilegedCommunicationError):
        texting.send_text(owner, rid, add_contact(rid, "attorney"), "private", NOW, messaging=svc)


def test_the_database_refuses_stored_attorney_message_text(
    owner, seeded, make_resident, add_contact
):
    rid = make_resident()
    cid = add_contact(rid, "attorney")
    with owner.begin_nested():
        owner.add(
            Message(
                resident_id=rid,
                contact_id=cid,
                direction="out",
                body="secret",
                privileged=True,
                monitored=False,
                created_at=NOW,
            )
        )
        with pytest.raises(IntegrityError):
            owner.flush()


def test_blocked_contacts_cannot_be_texted(owner, seeded, make_resident, add_contact):
    rid = make_resident()
    give(owner, rid, 450)
    with pytest.raises(texting.TextDenied) as e:
        texting.send_text(owner, rid, add_contact(rid, blocked=True), "hi", NOW)
    assert e.value.code == "CONTACT_UNAVAILABLE"


# ======================= chess =======================
def test_there_is_no_chat_anywhere_in_chess():
    from isd.interfaces.chess import ChessProvider

    cols = {c.name for t in (ChessGame, ChessMove) for c in t.__table__.columns}
    assert not any(
        w in name for name in cols for w in ("chat", "message", "text", "note", "comment")
    )
    methods = {m for m in dir(ChessProvider) if not m.startswith("_")}
    assert methods == {"new_game", "submit_move"}
    from isd.main import app

    paths = [p for p in app.openapi()["paths"] if "chess" in p]
    assert paths and not [p for p in paths if "chat" in p or "message" in p]


# ======================= reading =======================
def test_reading_catalogs_follow_tiers_and_the_allow_list(
    owner, seeded, reference_data, make_resident, make_staff
):
    rid = make_resident()
    listing = {i["id"]: i for i in reading.list_items(owner, rid, NOW)}
    assert listing["tortoise-hare"]["allowed"] and not listing["preamble"]["allowed"]
    assert listing["preamble"]["reasons"][0]["code"] == "TIER_LOCKED"
    assert reading.read_item(owner, rid, "tortoise-hare", NOW)["text"].startswith("A hare")
    with pytest.raises(reading.ReadingDenied) as e:
        reading.read_item(owner, rid, "preamble", NOW)
    assert e.value.code == "FEATURE_LOCKED"
    give(owner, rid, 450)
    assert reading.read_item(owner, rid, "preamble", NOW)["title"].startswith("Preamble")

    admin = Actor(make_staff("admin").id, "admin")
    src = reading.list_sources(owner)[0]
    reading.set_source_active(owner, admin, src.id, False)  # un-approve the bundled source
    with pytest.raises(reading.ReadingDenied) as e:
        reading.read_item(owner, rid, "tortoise-hare", NOW)
    assert e.value.code == "SOURCE_NOT_APPROVED"
    # only the protected baseline texts (legal, religious) stay open without an approved source
    assert {i["catalog"] for i in reading.list_items(owner, rid, NOW) if i["allowed"]} == {
        "legal",
        "religious",
    }
    with pytest.raises(ValueError):
        reading.add_source(owner, admin, "Some website", "external", "http://insecure.example", NOW)
    ok = reading.add_source(
        owner, admin, "Approved library", "external", "https://library.example", NOW
    )
    assert (
        ok.active
        and owner.execute(select(AuditLog).where(AuditLog.action == "content_source_added")).first()
    )


# ======================= rec time =======================
def test_baseline_indoor_slots_are_always_open_outdoor_needs_a_high_tier(
    owner, seeded, make_resident
):
    rid = make_resident()
    today = NOW.date()
    view = rec.day_view(owner, rid, today, NOW)
    assert view["baseline_minutes"] == 60
    kinds = {(s["kind"], s["allowed"]) for s in view["slots"] if s["kind"] in ("indoor", "outdoor")}
    assert kinds == {("indoor", True), ("outdoor", False)}
    programs = {s["title"]: s["allowed"] for s in view["slots"] if s["kind"] == "program"}
    assert programs == {"Life skills class": True, "Workplace math": False}  # advanced is tier 3+
    assert all(s["allowed"] for s in view["slots"] if s["kind"] == "visit")
    rec.book(owner, rid, today, "09:00", NOW)
    with pytest.raises(rec.RecDenied) as e:
        rec.book(owner, rid, today, "09:00", NOW)
    assert e.value.code == "ALREADY_BOOKED"
    with pytest.raises(rec.RecDenied) as e:
        rec.book(owner, rid, today, "10:00", NOW)
    assert e.value.code == "FEATURE_LOCKED"
    give(owner, rid, 2500)  # tier 9: outdoor
    rec.book(owner, rid, today, "10:00", NOW)
    assert rec.cancel(owner, rid, today, "10:00") and not rec.cancel(owner, rid, today, "10:00")


def test_rec_capacity_and_day_limits(owner, seeded, make_resident):
    today = NOW.date()
    for _ in range(6):
        rec.book(owner, make_resident(), today, "13:30", NOW)
    with pytest.raises(rec.RecDenied) as e:
        rec.book(owner, make_resident(), today, "13:30", NOW)
    assert e.value.code == "FULL"
    rid = make_resident()
    for day, code in (
        (today - timedelta(days=1), "BAD_DAY"),
        (today + timedelta(days=9), "BAD_DAY"),
    ):
        with pytest.raises(rec.RecDenied) as e:
            rec.book(owner, rid, day, "09:00", NOW)
        assert e.value.code == code
    with pytest.raises(rec.RecDenied) as e:
        rec.book(owner, rid, today, "03:00", NOW)
    assert e.value.code == "BAD_SLOT"
