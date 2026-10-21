from datetime import timedelta

from sqlalchemy import select

from isd.models import (
    AuditLog,
    CallRecord,
    Cell,
    Contact,
    Device,
    DeviceAssignment,
    PointEvent,
    TierHistory,
)
from isd.services import calls, mirror, points, sanctions
from isd.services.audit import SYSTEM, Actor
from isd.services.daily import run_daily
from isd.services.entitlement_service import earned_tier
from tests.conftest import NOW


def assign(owner, rid, days_before):
    c, d = Cell(code=f"DC-{rid}"), Device(code=f"DD-{rid}")
    owner.add_all([c, d])
    owner.flush()
    owner.add(
        DeviceAssignment(
            device_id=d.id,
            cell_id=c.id,
            resident_id=rid,
            assigned_at=NOW - timedelta(days=days_before),
        )
    )
    owner.flush()


def clean_days(owner, rid):
    return [
        p.reason
        for p in owner.execute(
            select(PointEvent).where(PointEvent.resident_id == rid, PointEvent.kind == "clean_day")
        ).scalars()
    ]


def test_clean_day_is_worth_two_points_and_is_awarded_once(owner, seeded, make_resident):
    rid = make_resident()
    assign(owner, rid, 10)
    day = (NOW - timedelta(days=1)).date()
    first = run_daily(owner, NOW, for_day=day)
    assert first["clean_days_awarded"] >= 1 and clean_days(owner, rid) == [day.isoformat()]
    run_daily(owner, NOW + timedelta(minutes=5), for_day=day)  # run again: nothing new
    assert clean_days(owner, rid) == [day.isoformat()]
    assert points.total_points(owner, rid, NOW + timedelta(hours=1)) == 2
    run_daily(owner, NOW + timedelta(days=1), for_day=NOW.date())  # the next day adds one more
    assert len(clean_days(owner, rid)) == 2


def test_no_clean_day_for_a_day_with_a_confirmed_infraction(
    owner, seeded, make_resident, make_staff
):
    rid = make_resident()
    assign(owner, rid, 10)
    day = NOW.date()
    sanctions.issue_sanction(owner, make_staff("officer"), rid, "DISRUPT", NOW + timedelta(hours=2))
    run_daily(owner, NOW + timedelta(hours=23), for_day=day)
    assert clean_days(owner, rid) == []  # that day had a confirmed infraction
    run_daily(owner, NOW + timedelta(days=1, hours=23), for_day=day + timedelta(days=1))
    assert clean_days(owner, rid) == [(day + timedelta(days=1)).isoformat()]


def test_no_points_for_days_before_the_resident_had_a_device(owner, seeded, make_resident):
    rid = make_resident()
    assign(owner, rid, 0)  # assigned today
    run_daily(owner, NOW, for_day=NOW.date() - timedelta(days=1))
    assert clean_days(owner, rid) == []
    run_daily(owner, NOW + timedelta(hours=23), for_day=NOW.date())
    assert clean_days(owner, rid) == [NOW.date().isoformat()]


def test_the_delayed_weekly_tier_drop_finally_happens(owner, seeded, make_resident):
    rid = make_resident()
    assign(owner, rid, 30)
    points.record_points(
        owner, SYSTEM, rid, "seed_adjustment", 450, "system", NOW - timedelta(days=20)
    )
    points.evaluate_tier(owner, rid, NOW - timedelta(days=20))
    assert earned_tier(owner, rid, NOW) == 4
    points.record_points(owner, SYSTEM, rid, "seed_adjustment", -300, "staff", NOW)  # 150 points
    points.evaluate_tier(owner, rid, NOW)
    assert earned_tier(owner, rid, NOW) == 3  # one level at once, never more
    for d in (1, 3, 6):
        run_daily(owner, NOW + timedelta(days=d), for_day=(NOW + timedelta(days=d - 1)).date())
        assert earned_tier(owner, rid, NOW + timedelta(days=d)) == 3  # still inside the 7 days
    run_daily(owner, NOW + timedelta(days=7), for_day=(NOW + timedelta(days=6)).date())
    assert earned_tier(owner, rid, NOW + timedelta(days=7)) == 2  # the second drop, a week later
    drops = (
        owner.execute(
            select(TierHistory)
            .where(TierHistory.resident_id == rid, TierHistory.to_tier < TierHistory.from_tier)
            .order_by(TierHistory.at)
        )
        .scalars()
        .all()
    )
    assert len(drops) == 2 and drops[1].at - drops[0].at >= timedelta(days=7)


def test_housekeeping_closes_abandoned_calls_and_stale_mirror_sessions(
    owner, seeded, make_resident, make_staff
):
    rid = make_resident()
    assign(owner, rid, 5)
    cid = Contact(resident_id=rid, name="Synthetic Contact", type="family", phone_ref="555-0100")
    owner.add(cid)
    owner.flush()
    call = calls.start_call(owner, rid, cid.id, NOW)
    sup = make_staff("supervisor")
    m = mirror.start(owner, Actor(sup.id, "supervisor"), rid, "checking something out", NOW)
    result = run_daily(owner, NOW + timedelta(hours=3), for_day=NOW.date())
    assert owner.get(CallRecord, call.id).status == "timed_out"
    assert result["mirror_sessions_closed"] == 1
    ended = owner.execute(select(AuditLog).where(AuditLog.action == "mirror_ended")).scalars().all()
    assert any(e.payload["session_id"] == m.id for e in ended)
