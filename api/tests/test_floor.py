"""Phase 13: the unit schedule, out-of-cell movement, and welfare flags that must be handled."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from isd.engine.authority import Evidence
from isd.models import (
    AuditLog,
    Cell,
    Device,
    DeviceAssignment,
    OutOfCellEvent,
    OutOfCellLog,
    ScheduleBlock,
    WelfareFlag,
)
from isd.services import (
    daily,
    movement,
    out_of_cell,
    rec,
    sanctions,
    schedule,
    staff_views,
    welfare,
)
from isd.services.audit import SYSTEM
from isd.services.config_store import get_current, set_config
from tests.conftest import NOW
from tests.test_phase7_services import give

TODAY = NOW.date()


def place(owner, rid, unit="A", days_ago=0):
    cell, dev = Cell(code=f"U{unit}-{rid}", unit=unit), Device(code=f"D{unit}-{rid}")
    owner.add_all([cell, dev])
    owner.flush()
    owner.add(
        DeviceAssignment(
            device_id=dev.id,
            cell_id=cell.id,
            resident_id=rid,
            assigned_at=NOW - timedelta(days=days_ago),
        )
    )
    owner.flush()


@pytest.fixture
def staff(make_staff):
    return {r: make_staff(r) for r in ("officer", "supervisor", "admin", "auditor")}


# ======================= schedule =======================
def test_a_day_without_blocks_uses_the_template_and_becoming_real_is_repeat_safe(
    owner, seeded, make_resident
):
    rid = make_resident()
    place(owner, rid, "B")
    view = rec.day_view(owner, rid, TODAY, NOW)
    assert (
        view["unit"] == "B" and len(view["slots"]) == 8
    )  # 3 indoor, 2 outdoor, 2 programs, 1 visit
    assert all(s["block_id"] is None for s in view["slots"])  # nothing saved yet
    assert schedule.ensure_day(owner, "B", TODAY, NOW) == 8
    assert schedule.ensure_day(owner, "B", TODAY, NOW) == 0
    assert all(s["block_id"] for s in rec.day_view(owner, rid, TODAY, NOW)["slots"])
    assert schedule.generate(owner, NOW, 3) > 0 and schedule.generate(owner, NOW, 3) == 0


def test_staff_changes_one_units_day_and_other_units_are_untouched(
    owner, seeded, make_resident, staff
):
    a, b = make_resident(), make_resident()
    place(owner, a, "A")
    place(owner, b, "B")
    block = schedule.add_block(
        owner,
        staff["supervisor"],
        "A",
        TODAY,
        "program",
        "20:00",
        45,
        5,
        "Book club",
        "basic_education",
        "added at the unit's request",
        NOW,
    )
    titles = lambda rid: {s["title"] for s in rec.day_view(owner, rid, TODAY, NOW)["slots"]}  # noqa: E731
    assert "Book club" in titles(a) and "Book club" not in titles(b)
    assert len(rec.day_view(owner, a, TODAY, NOW)["slots"]) == 9  # the template stayed
    with pytest.raises(schedule.ScheduleError) as e:
        schedule.add_block(
            owner,
            staff["supervisor"],
            "A",
            TODAY,
            "program",
            "20:00",
            45,
            5,
            "Again",
            None,
            "second try here",
            NOW,
        )
    assert e.value.code == "DUPLICATE"
    audit = owner.execute(
        select(AuditLog).where(AuditLog.action == "schedule_block_added")
    ).scalar()
    assert audit.payload["reason"] == "added at the unit's request" and block.id


def test_schedule_changes_need_a_reason_a_valid_block_and_a_day_not_in_the_past(
    owner, seeded, staff
):
    sup = staff["supervisor"]
    for kwargs, code in (
        ({"kind": "party"}, "BAD_KIND"),
        ({"start": "25:00"}, "BAD_BLOCK"),
        ({"minutes": 0}, "BAD_BLOCK"),
        ({"reason": "no"}, "REASON_REQUIRED"),
        ({"day": TODAY - timedelta(days=1)}, "PAST"),
        ({"kind": "visit", "title": ""}, "BAD_BLOCK"),
    ):
        args = dict(
            unit="A",
            day=TODAY,
            kind="program",
            start="19:00",
            minutes=30,
            capacity=4,
            title="x",
            required_feature=None,
            reason="a good reason",
            now=NOW,
        )
        args.update(kwargs)
        with pytest.raises(schedule.ScheduleError) as e:
            schedule.add_block(owner, sup, **args)
        assert e.value.code == code


def test_a_cancelled_block_cannot_be_booked_and_shows_as_cancelled(
    owner, seeded, make_resident, staff
):
    rid = make_resident()
    schedule.ensure_day(owner, "A", TODAY, NOW)
    block = owner.execute(
        select(ScheduleBlock).where(ScheduleBlock.kind == "indoor", ScheduleBlock.start == "09:00")
    ).scalar()
    rec.book(owner, rid, TODAY, "09:00", NOW)
    schedule.cancel_block(owner, staff["supervisor"], block.id, "staff shortage today", NOW)
    slot = next(
        s
        for s in rec.day_view(owner, rid, TODAY, NOW)["slots"]
        if s["slot"] == "09:00" and s["kind"] == "indoor"
    )
    assert slot["cancelled"] and not slot["allowed"]
    with pytest.raises(rec.RecDenied) as e:
        rec.book(owner, make_resident(), TODAY, "09:00", NOW)
    assert e.value.code == "CANCELLED"


def test_capacity_is_per_unit_block(owner, seeded, make_resident):
    cfg = dict(get_current(owner, "rec").payload)
    cfg["capacity"] = 1
    set_config(owner, SYSTEM, "rec", cfg, "test: tiny rooms")
    a1, a2, b1 = make_resident(), make_resident(), make_resident()
    for rid, unit in ((a1, "A"), (a2, "A"), (b1, "B")):
        place(owner, rid, unit)
    rec.book(owner, a1, TODAY, "13:30", NOW)
    with pytest.raises(rec.RecDenied) as e:
        rec.book(owner, a2, TODAY, "13:30", NOW)
    assert e.value.code == "FULL"
    rec.book(owner, b1, TODAY, "13:30", NOW)  # unit B has its own room


def test_eligibility_comes_from_the_entitlement_function(owner, seeded, make_resident, staff):
    low, t3, t9 = make_resident(), make_resident(), make_resident()
    give(owner, t3, 250)
    give(owner, t9, 2500)
    assert rec.book(owner, low, TODAY, "11:00", NOW).kind == "program"  # basic: baseline
    with pytest.raises(rec.RecDenied) as e:
        rec.book(owner, low, TODAY, "16:30", NOW)  # advanced program
    assert e.value.code == "FEATURE_LOCKED"
    assert rec.book(owner, t3, TODAY, "16:30", NOW).kind == "program"
    with pytest.raises(rec.RecDenied):
        rec.book(owner, t3, TODAY, "10:00", NOW)  # outdoor needs tier 9
    assert rec.book(owner, t9, TODAY, "10:00", NOW).kind == "outdoor"
    assert rec.book(owner, low, TODAY, "14:00", NOW).kind == "visit"


def test_a_sanction_locks_outdoor_but_never_the_indoor_baseline(
    owner, seeded, make_resident, make_staff
):
    rid = make_resident()
    give(owner, rid, 2500)
    officer, sup, other = make_staff("officer"), make_staff("supervisor"), make_staff("officer")
    s = sanctions.issue_sanction(
        owner, officer, rid, "CAM_BLOCK", NOW, Evidence("second_staff_report", reporter_id=other.id)
    )
    sanctions.confirm_sanction(owner, sup, s.id, NOW + timedelta(minutes=1))
    later = NOW + timedelta(hours=1)
    slots = {
        (x["kind"], x["slot"]): x["allowed"]
        for x in rec.day_view(owner, rid, TODAY, later)["slots"]
    }
    assert slots[("indoor", "09:00")] and not slots[("outdoor", "10:00")]


# ======================= movement =======================
def at(h, m=0, day=0):
    return datetime(NOW.year, NOW.month, NOW.day, tzinfo=UTC) + timedelta(
        days=day, hours=h, minutes=m
    )


def test_tapping_out_and_in_counts_the_time_and_writes_the_days_total(
    owner, seeded, make_resident, staff
):
    rid = make_resident()
    o = staff["officer"]
    movement.tap_out(owner, o, rid, "indoor", at(9), at=at(9))
    assert [r["resident_id"] for r in movement.who_is_out(owner, at(9, 30))] == [rid]
    movement.tap_in(owner, o, rid, at(10), at=at(10))
    assert out_of_cell.by_day(owner, rid, TODAY, TODAY) == {TODAY: 60}
    assert movement.who_is_out(owner, at(10, 5)) == []
    movement.tap_out(owner, o, rid, "outdoor", at(15), at=at(15))
    movement.tap_in(owner, o, rid, at(15, 30), at=at(15, 30))
    assert out_of_cell.by_day(owner, rid, TODAY, TODAY) == {TODAY: 90}  # a later row replaces it
    rows = owner.execute(
        select(func.count(OutOfCellLog.id)).where(OutOfCellLog.resident_id == rid)
    ).scalar()
    assert rows == 2  # the first entry is kept; the correction is a new row


def test_a_stuck_open_interval_runs_to_now_and_midnight_splits_the_day(
    owner, seeded, make_resident, staff
):
    rid = make_resident()
    movement.tap_out(owner, staff["officer"], rid, "program", at(23), at=at(23))
    movement.tap_in(owner, staff["officer"], rid, at(1, 30, day=1), at=at(1, 30, day=1))
    assert out_of_cell.by_day(owner, rid, TODAY, TODAY + timedelta(days=1)) == {
        TODAY: 60,
        TODAY + timedelta(days=1): 90,
    }


@pytest.mark.parametrize(
    "first, second, code",
    [
        ("out", "out", "ALREADY_OUT"),
        ("in", None, "NOT_OUT"),
    ],
)
def test_impossible_movements_are_refused(owner, seeded, make_resident, staff, first, second, code):
    rid = make_resident()
    o = staff["officer"]
    with pytest.raises(movement.MovementError) as e:
        if first == "out":
            movement.tap_out(owner, o, rid, "indoor", at(9), at=at(9))
            movement.tap_out(owner, o, rid, "indoor", at(9, 5), at=at(9, 5))
        else:
            movement.tap_in(owner, o, rid, at(9))
    assert e.value.code == code


def test_times_must_be_recent_not_in_the_future_and_in_order(owner, seeded, make_resident, staff):
    rid, o = make_resident(), staff["officer"]
    with pytest.raises(movement.MovementError) as e:
        movement.tap_out(owner, o, rid, "indoor", at(9), at=at(12))
    assert e.value.code == "FUTURE"
    with pytest.raises(movement.MovementError) as e:
        movement.tap_out(owner, o, rid, "indoor", at(9) + timedelta(days=2), at=at(9))
    assert e.value.code == "TOO_OLD"
    movement.tap_out(owner, o, rid, "indoor", at(10), at=at(10))
    with pytest.raises(movement.MovementError) as e:
        movement.tap_in(owner, o, rid, at(10, 30), at=at(9, 30))
    assert e.value.code == "OUT_OF_ORDER"
    with pytest.raises(movement.MovementError) as e:
        movement.tap_out(owner, o, make_resident(), "dancing", at(9))
    assert e.value.code == "BAD_ACTIVITY"


def test_bulk_actions_report_each_resident_and_one_problem_does_not_block_the_rest(
    owner, seeded, make_resident, staff
):
    a, b, c = make_resident(), make_resident(), make_resident()
    movement.tap_out(owner, staff["officer"], b, "indoor", at(8), at=at(8))
    out = movement.bulk_out(owner, staff["officer"], [a, b, c, a], "outdoor", at(9))
    assert [(r["resident_id"], r["ok"], r["code"]) for r in out] == [
        (a, True, None),
        (b, False, "ALREADY_OUT"),
        (c, True, None),
    ]
    done = movement.bulk_in(owner, staff["officer"], [a, b, c, 999999], at(10))
    assert [(r["ok"]) for r in done] == [True, True, True, False]
    assert movement.who_is_out(owner, at(10, 1)) == []
    with pytest.raises(movement.MovementError):
        movement.bulk_out(owner, staff["officer"], [], "indoor", at(9))


def test_movement_events_are_append_only(owner, seeded, make_resident, staff):
    rid = make_resident()
    movement.tap_out(owner, staff["officer"], rid, "indoor", at(9), at=at(9))
    for sql in ("UPDATE out_of_cell_events SET at = at", "DELETE FROM out_of_cell_events"):
        with pytest.raises(DBAPIError):
            with owner.begin_nested():
                owner.execute(text(sql))
    assert owner.execute(select(func.count(OutOfCellEvent.id))).scalar() >= 1


def test_who_is_out_can_be_limited_to_a_unit(owner, seeded, make_resident, staff):
    a, b = make_resident(), make_resident()
    place(owner, a, "A")
    place(owner, b, "B")
    movement.bulk_out(owner, staff["officer"], [a, b], "indoor", at(9))
    assert [r["resident_id"] for r in movement.who_is_out(owner, at(9, 10), "B")] == [b]
    assert {r["unit"] for r in movement.who_is_out(owner, at(9, 10))} == {"A", "B"}


# ---------------- scheduled versus actual ----------------
def test_the_discrepancy_report_compares_signups_with_who_was_actually_out(
    owner, seeded, make_resident, staff
):
    attended, partial, missed = make_resident(), make_resident(), make_resident()
    for rid in (attended, partial, missed):
        place(owner, rid, "A")
        rec.book(owner, rid, TODAY, "09:00", NOW)  # a 60-minute indoor block
    o = staff["officer"]
    movement.tap_out(owner, o, attended, "indoor", at(9), at=at(9))
    movement.tap_in(owner, o, attended, at(9, 50), at=at(9, 50))
    movement.tap_out(owner, o, partial, "indoor", at(9), at=at(9))
    movement.tap_in(owner, o, partial, at(9, 15), at=at(9, 15))
    report = movement.discrepancies(owner, TODAY, at(12), "A")
    block = next(b for b in report["blocks"] if b["kind"] == "indoor" and b["start"] == "09:00")
    assert (block["booked"], block["attended"], block["partial"], block["missed"]) == (3, 1, 1, 1)
    assert len(block["missed_residents"]) == 1
    people = {r["resident_id"]: r for r in report["residents"]}
    assert people[attended]["scheduled_minutes"] == 60 and people[attended]["actual_minutes"] == 50
    assert not people[attended]["short_of_schedule"]  # day not over yet: nothing is called short
    tomorrow = at(12, day=1)
    later = movement.discrepancies(owner, TODAY, tomorrow, "A")
    flagged = {r["resident_id"]: r for r in later["residents"]}
    assert flagged[missed]["short_of_schedule"] and flagged[missed]["below_minimum"]
    assert flagged[partial]["short_of_schedule"] and not flagged[attended]["short_of_schedule"]


def test_the_daily_export_is_audited_and_has_one_row_per_resident(
    owner, seeded, make_resident, staff
):
    rid = make_resident()
    place(owner, rid, "A")
    movement.tap_out(owner, staff["officer"], rid, "indoor", at(9), at=at(9))
    movement.tap_in(owner, staff["officer"], rid, at(9, 40), at=at(9, 40))
    csv_text, media = movement.export_day(owner, staff["auditor"], TODAY, at(12), "A", "csv")
    lines = csv_text.strip().splitlines()
    assert media == "text/csv" and lines[0].startswith("day,unit,resident,scheduled_minutes")
    assert any(",40," in line for line in lines[1:])
    body, media = movement.export_day(owner, staff["auditor"], TODAY, at(12), "A", "json")
    assert media == "application/json" and '"residents"' in body
    exported = (
        owner.execute(select(AuditLog).where(AuditLog.action == "out_of_cell_export"))
        .scalars()
        .all()
    )
    assert len(exported) == 2 and exported[0].actor_role == "auditor"


# ======================= minimum time on the dashboard =======================
def test_residents_below_the_minimum_surface_on_the_dashboard(owner, seeded, make_resident, staff):
    short, fine = make_resident(), make_resident()
    for rid in (short, fine):
        place(owner, rid, "A", days_ago=10)
    yesterday = TODAY - timedelta(days=1)
    out_of_cell.record(owner, staff["officer"], short, yesterday, 20, "facility", NOW)
    out_of_cell.record(owner, staff["officer"], fine, yesterday, 75, "facility", NOW)
    rows = out_of_cell.below_minimum(owner, NOW)
    assert [
        (r["resident_id"], r["minutes"], r["minimum"])
        for r in rows
        if r["resident_id"] in (short, fine)
    ] == [(short, 20, 60)]
    summary = staff_views.summary(owner, staff["officer"].id, "officer", NOW)
    assert summary["below_minimum"] >= 1
    assert any(
        f["type"] == "out_of_cell_below"
        for r in welfare.all_flags(owner, NOW)
        if r["resident_id"] == short
        for f in r["flags"]
    )
    out_of_cell.record(owner, staff["officer"], short, yesterday, 90, "facility", NOW)  # corrected
    assert not [r for r in out_of_cell.below_minimum(owner, NOW) if r["resident_id"] == short]


# ======================= welfare flags that must be handled =======================
def quiet_resident(owner, make_resident):
    rid = make_resident()
    place(owner, rid, "A", days_ago=10)  # 10 days on the unit, never any contact
    return rid


def test_a_flag_is_stored_with_the_residents_own_numbers_and_only_raised_once(
    owner, seeded, make_resident
):
    rid = quiet_resident(owner, make_resident)
    first = welfare.sync_flags(owner, NOW)
    assert first["raised"] >= 1
    assert welfare.sync_flags(owner, NOW + timedelta(minutes=5)) == {
        "raised": 0,
        "escalated": 0,
        "cleared": 0,
    }
    flag = owner.execute(
        select(WelfareFlag).where(
            WelfareFlag.resident_id == rid, WelfareFlag.flag_type == "no_contact"
        )
    ).scalar()
    assert flag.status == "open" and flag.detail["days"] == 10 and flag.detail["never"] is True
    raised = (
        owner.execute(select(AuditLog).where(AuditLog.action == "welfare_flag_raised"))
        .scalars()
        .all()
    )
    assert any(a.target_id == str(rid) for a in raised)


def test_an_unacknowledged_flag_escalates_to_a_supervisor_after_the_configured_time(
    owner, seeded, make_resident, staff
):
    rid = quiet_resident(owner, make_resident)
    welfare.sync_flags(owner, NOW)
    escalate = get_current(owner, "welfare").payload["escalate_after_minutes"]
    just_before = NOW + timedelta(minutes=escalate - 1)
    assert welfare.sync_flags(owner, just_before)["escalated"] == 0
    flags = [
        f
        for r in welfare.all_flags(owner, just_before)
        if r["resident_id"] == rid
        for f in r["flags"]
    ]
    assert flags and not any(f["escalated"] for f in flags)
    after = NOW + timedelta(minutes=escalate)
    assert welfare.sync_flags(owner, after)["escalated"] >= 1
    flags = [
        f for r in welfare.all_flags(owner, after) if r["resident_id"] == rid for f in r["flags"]
    ]
    assert all(f["escalated"] for f in flags if f["type"] == "no_contact")
    assert welfare.sync_flags(owner, after + timedelta(hours=5))["escalated"] == 0  # only once
    alert = (
        owner.execute(select(AuditLog).where(AuditLog.action == "welfare_escalated"))
        .scalars()
        .all()
    )
    assert any(a.target_id == str(rid) and a.reason_code == "WELFARE_ESCALATED" for a in alert)
    summary = staff_views.summary(owner, staff["supervisor"].id, "supervisor", after)
    assert summary["welfare_escalated"] >= 1


def test_an_escalated_flag_can_only_be_handled_by_a_supervisor_and_needs_an_action(
    owner, seeded, make_resident, staff
):
    rid = quiet_resident(owner, make_resident)
    welfare.sync_flags(owner, NOW)
    late = NOW + timedelta(hours=13)
    welfare.sync_flags(owner, late)
    with pytest.raises(welfare.WelfareError) as e:
        welfare.acknowledge(owner, staff["officer"], rid, "no_contact", "I spoke with them", late)
    assert e.value.code == "NEEDS_SUPERVISOR"
    for bad_action, code in (("shrug", "BAD_ACTION"),):
        with pytest.raises(welfare.WelfareError) as e:
            welfare.acknowledge(
                owner, staff["supervisor"], rid, "no_contact", "spoke with them", late, bad_action
            )
        assert e.value.code == code
    with pytest.raises(welfare.WelfareError) as e:
        welfare.acknowledge(owner, staff["supervisor"], rid, "no_contact", "ok", late)
    assert e.value.code == "NOTE_REQUIRED"
    welfare.acknowledge(
        owner,
        staff["supervisor"],
        rid,
        "no_contact",
        "Visited the cell; they are well",
        late,
        "referred_mental_health",
    )
    flag = owner.execute(
        select(WelfareFlag).where(
            WelfareFlag.resident_id == rid, WelfareFlag.flag_type == "no_contact"
        )
    ).scalar()
    assert (flag.status, flag.action) == ("acknowledged", "referred_mental_health")
    assert not any(
        f["type"] == "no_contact"
        for r in welfare.all_flags(owner, late)
        if r["resident_id"] == rid
        for f in r["flags"]
    )
    entry = (
        owner.execute(select(AuditLog).where(AuditLog.action == "welfare_ack")).scalars().all()[-1]
    )
    assert entry.payload["action"] == "referred_mental_health" and entry.actor_role == "supervisor"
    with pytest.raises(welfare.WelfareError) as e:  # nothing left to acknowledge
        welfare.acknowledge(
            owner, staff["supervisor"], rid, "no_contact", "again for good measure", late
        )
    assert e.value.code == "NO_OPEN_FLAG"


def test_an_officer_can_handle_a_flag_before_it_escalates_and_it_does_not_escalate_afterward(
    owner, seeded, make_resident, staff
):
    rid = quiet_resident(owner, make_resident)
    welfare.sync_flags(owner, NOW)
    welfare.acknowledge(
        owner,
        staff["officer"],
        rid,
        "no_contact",
        "Checked in, resident is fine",
        NOW + timedelta(hours=1),
    )
    welfare.sync_flags(owner, NOW + timedelta(days=2))
    handled = owner.execute(
        select(WelfareFlag).where(
            WelfareFlag.resident_id == rid, WelfareFlag.flag_type == "no_contact"
        )
    ).scalar()
    assert handled.status == "acknowledged" and handled.escalated_at is None
    quiet_until = NOW + timedelta(
        days=get_current(owner, "welfare").payload["ack_suppress_days"], hours=2
    )
    assert welfare.sync_flags(owner, quiet_until)["raised"] >= 1  # still true, so it comes back


def test_a_flag_whose_condition_has_gone_clears_itself(owner, seeded, make_resident, staff):
    rid = quiet_resident(owner, make_resident)
    welfare.sync_flags(owner, NOW)
    contact = Contact(
        resident_id=rid, name="Synthetic Contact", type="family", phone_ref="555-0188"
    )
    owner.add(contact)
    owner.flush()
    from isd.models import CallRecord

    owner.add(
        CallRecord(
            resident_id=rid,
            contact_id=contact.id,
            contact_type="family",
            privileged=False,
            monitored=True,
            provider_ref="x",
            started_at=NOW,
            max_seconds=60,
            status="completed",
            duration_seconds=30,
            medium="voice",
        )
    )
    owner.flush()
    out = welfare.sync_flags(owner, NOW + timedelta(hours=1))
    assert out["cleared"] >= 1
    flag = owner.execute(
        select(WelfareFlag).where(
            WelfareFlag.resident_id == rid, WelfareFlag.flag_type == "no_contact"
        )
    ).scalar()
    assert flag.status == "cleared" and flag.cleared_at


def test_the_daily_job_syncs_flags_and_makes_the_schedule(owner, seeded, make_resident):
    quiet_resident(owner, make_resident)
    result = daily.run_daily(owner, NOW + timedelta(hours=14))
    assert result["welfare"]["raised"] >= 1 and result["schedule_blocks_made"] > 0
    assert daily.run_daily(owner, NOW + timedelta(hours=14, minutes=1))["schedule_blocks_made"] == 0


from isd.models import Contact  # noqa: E402


# ---------------- over HTTP ----------------
@pytest.mark.usefixtures("committed_config", "committed_reference")
def test_floor_routes_enforce_roles_and_validate_input(client, kiosk, owner_engine):
    import uuid

    from sqlalchemy.orm import Session

    from isd.auth import make_token
    from isd.models import Staff

    rid, _, _ = kiosk()
    heads = {}
    with Session(owner_engine) as s, s.begin():
        for role in ("officer", "supervisor", "admin", "auditor"):
            st = Staff(username=f"{role}_{uuid.uuid4().hex[:8]}", role=role, password_hash="x")
            s.add(st)
            s.flush()
            heads[role] = {"Authorization": f"Bearer {make_token(st.id)}"}
    today = datetime.now(UTC).date().isoformat()

    out = {"resident_ids": [rid], "activity": "indoor"}
    assert client.post("/staff/movement/out", json=out).status_code == 401
    assert client.post("/staff/movement/out", json=out, headers=heads["auditor"]).status_code == 403
    for bad in ({"resident_ids": [], "activity": "indoor"}, {**out, "extra": 1}):
        assert (
            client.post("/staff/movement/out", json=bad, headers=heads["officer"]).status_code
            == 422
        )
    done = client.post("/staff/movement/out", json=out, headers=heads["officer"]).json()
    assert done == [{"resident_id": rid, "ok": True, "code": None}]
    again = client.post("/staff/movement/out", json=out, headers=heads["officer"]).json()
    assert again[0]["code"] == "ALREADY_OUT"
    roster = client.get("/staff/movement/now", headers=heads["auditor"]).json()
    assert any(r["resident_id"] == rid for r in roster)
    back = client.post("/staff/movement/in", json={"resident_ids": [rid]}, headers=heads["officer"])
    assert back.json()[0]["ok"] is True

    report = client.get(
        f"/staff/movement/discrepancies?day={today}", headers=heads["auditor"]
    ).json()
    assert report["day"] == today and "blocks" in report and "residents" in report
    assert (
        client.get(f"/staff/movement/export?day={today}", headers=heads["officer"]).status_code
        == 403
    )
    exported = client.get(f"/staff/movement/export?day={today}&unit=A", headers=heads["auditor"])
    assert exported.status_code == 200 and exported.headers["content-type"].startswith("text/csv")
    assert "attachment" in exported.headers["content-disposition"]
    assert (
        client.get(
            f"/staff/movement/export?day={today}&format=xml", headers=heads["auditor"]
        ).status_code
        == 422
    )

    block = {
        "unit": "A",
        "day": today,
        "kind": "program",
        "start": "21:00",
        "minutes": 30,
        "capacity": 5,
        "title": "Evening study",
        "required_feature": "basic_education",
        "reason": "unit request for evening study",
    }
    assert (
        client.post("/staff/schedule/blocks", json=block, headers=heads["officer"]).status_code
        == 403
    )
    made = client.post("/staff/schedule/blocks", json=block, headers=heads["supervisor"])
    assert made.status_code == 201
    dup = client.post("/staff/schedule/blocks", json=block, headers=heads["supervisor"])
    assert dup.status_code == 409 and dup.json()["detail"]["code"] == "DUPLICATE"
    assert (
        client.post(
            "/staff/schedule/blocks", json={**block, "x": 1}, headers=heads["supervisor"]
        ).status_code
        == 422
    )
    view = client.get(f"/staff/schedule?unit=A&day={today}", headers=heads["officer"]).json()
    assert view["explicit"] and any(b["title"] == "Evening study" for b in view["blocks"])
    cancel = f"/staff/schedule/blocks/{made.json()['id']}/cancel"
    assert (
        client.post(cancel, json={"reason": "nope"}, headers=heads["supervisor"]).status_code == 409
    )
    assert (
        client.post(
            cancel, json={"reason": "no one signed up"}, headers=heads["supervisor"]
        ).json()["status"]
        == "cancelled"
    )
    assert client.post("/staff/schedule/generate", headers=heads["supervisor"]).status_code == 403
    assert client.post("/staff/schedule/generate?days=2", headers=heads["admin"]).status_code == 200
    assert "A" in client.get("/staff/schedule/units", headers=heads["auditor"]).json()

    ack = {"resident_id": rid, "flag_type": "no_contact", "note": "checked in", "action": "shrug"}
    assert client.post("/staff/welfare/ack", json=ack, headers=heads["officer"]).status_code == 422
    ack["action"] = "checked_in"
    none = client.post("/staff/welfare/ack", json=ack, headers=heads["officer"])
    assert none.status_code == 409 and none.json()["detail"]["code"] == "NO_OPEN_FLAG"
    below = client.get("/staff/out-of-cell/below-minimum", headers=heads["auditor"])
    assert below.status_code == 200 and isinstance(below.json(), list)
    summary = client.get("/staff/summary", headers=heads["officer"]).json()
    assert {"below_minimum", "welfare_escalated", "welfare_flags"} <= set(summary)
