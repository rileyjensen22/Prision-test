"""The facility model: its shape, the grouped dashboard numbers, roster paging, and per-floor
recreation that respects each line's concurrency limit."""

from datetime import timedelta

import pytest
from sqlalchemy import func, select

from isd.models import (
    Cell,
    Device,
    DeviceAssignment,
    Floor,
    Hub,
    Line,
    RecArea,
    Resident,
    Sanction,
    ScheduleBlock,
)
from isd.services import facility_model, rec, schedule, staff_views
from isd.services.audit import SYSTEM
from isd.services.config_store import get_current, set_config
from tests.conftest import NOW

DEMO = {"hubs": 2, "lines_per_hub": 2, "floors_per_line": 3, "cells_per_floor": 4}


def count(owner, model):
    return owner.execute(select(func.count()).select_from(model)).scalar()


@pytest.fixture
def built(owner, seeded):
    """A small facility on top of the seeded config (the seeded fixture builds none)."""
    from isd.models import Site

    if owner.execute(select(Site.id)).first() is None:
        facility_model.build(owner, DEMO)
    return DEMO


def place(owner, code, cell):
    r = Resident(code=code, display_name="Synthetic")
    d = Device(code=f"D-{code}")
    owner.add_all([r, d])
    owner.flush()
    owner.add(
        DeviceAssignment(
            device_id=d.id, cell_id=cell.id, resident_id=r.id, assigned_at=NOW - timedelta(days=1)
        )
    )
    owner.flush()
    return r


def test_the_full_scale_is_five_hubs_of_six_lines_and_1920_cells(owner, seeded):
    full = facility_model.scale_named(owner, "full")
    assert full == {"hubs": 5, "lines_per_hub": 6, "floors_per_line": 4, "cells_per_floor": 16}
    from isd.models import Site

    if owner.execute(select(Site.id)).first():
        pytest.skip("this database already has a facility")
    cells = facility_model.build(owner, full)
    assert len(cells) == 5 * 6 * 4 * 16 == 1920
    assert (count(owner, Hub), count(owner, Line), count(owner, Floor)) == (5, 30, 120)
    assert count(owner, RecArea) == 30 * 8  # four day rooms and four yards on every line
    assert len({c.code for c in cells}) == 1920  # every cell has its own name
    assert all(c.unit == c.line_code for c in cells)  # the unit and the line are the same thing


def test_building_twice_is_refused(owner, built):
    with pytest.raises(facility_model.FacilityError) as e:
        facility_model.build(owner, DEMO)
    assert e.value.code == "EXISTS"


def test_the_overview_groups_cells_residents_and_locks_by_hub_line_and_floor(owner, built):
    cells = list(owner.execute(select(Cell).order_by(Cell.id)).scalars())
    h1 = [c for c in cells if c.code.startswith("H1-L1-F1")]
    a = place(owner, "FAC-A", h1[0])
    place(owner, "FAC-B", h1[1])
    place(owner, "FAC-C", next(c for c in cells if c.code.startswith("H2-L2-F3")))
    owner.add(
        Sanction(
            resident_id=a.id,
            infraction_code="DISRUPT",
            scope="communication",
            reason_code="DISRUPT",
            status="active",
            starts_at=NOW - timedelta(hours=1),
            ends_at=NOW + timedelta(hours=5),
        )
    )
    owner.flush()
    out = facility_model.overview(owner, NOW, timedelta(minutes=30))
    assert out["total"]["cells"] == 2 * 2 * 3 * 4 and out["total"]["occupied"] == 3
    hub1 = next(h for h in out["hubs"] if h["code"] == "H1")
    floor = next(
        f for ln in hub1["lines"] if ln["code"] == "H1-L1" for f in ln["floors"] if f["level"] == 1
    )
    assert (floor["cells"], floor["occupied"], floor["locked"]) == (4, 2, 1)
    assert floor["offline"] == 2  # their devices have never checked in
    assert out["total"]["locked"] == 1 and hub1["occupied"] == 2


def test_the_summary_comes_from_aggregates_and_matches_the_roster(owner, built):
    cells = list(owner.execute(select(Cell).order_by(Cell.id)).scalars())
    for i in range(5):
        place(owner, f"FAC-{i}", cells[i])
    summary = staff_views.summary(owner, 1, "admin", NOW)
    roster = staff_views.roster(owner, NOW)
    assert summary["residents"] == len(roster)
    assert summary["offline_devices"] == sum(r["offline"] for r in roster)


def test_the_roster_pages_and_filters_by_hub_line_floor_and_search(owner, built):
    cells = list(owner.execute(select(Cell).order_by(Cell.id)).scalars())
    for i, cell in enumerate(cells[:30]):
        place(owner, f"FAC-{i:02d}", cell)
    # `q` keeps these checks to the residents made here, whatever else the database holds
    everyone = staff_views.roster_page(owner, NOW, q="FAC-", limit=100)
    assert everyone["total"] == 30 and len(everyone["rows"]) == 30
    page = staff_views.roster_page(owner, NOW, q="FAC-", limit=10, offset=10)
    assert [r["code"] for r in page["rows"]] == [f"FAC-{i:02d}" for i in range(10, 20)]
    one_hub = staff_views.roster_page(owner, NOW, hub="H1", q="FAC-")
    assert one_hub["total"] == 24 and all(r["hub"] == "H1" for r in one_hub["rows"])
    one_line = staff_views.roster_page(owner, NOW, line="H1-L2", q="FAC-")
    assert all(r["line"] == "H1-L2" for r in one_line["rows"]) and one_line["total"] == 12
    one_floor = staff_views.roster_page(owner, NOW, line="H1-L1", floor=2, q="FAC-")
    assert one_floor["total"] == 4 and all(r["floor"] == 2 for r in one_floor["rows"])
    assert staff_views.roster_page(owner, NOW, q="FAC-07")["total"] == 1
    light = staff_views.lookup(owner, q="FAC-1", limit=3)
    assert len(light) == 3 and set(light[0]) >= {"resident_id", "code", "cell", "unit", "floor"}


def test_released_residents_leave_the_roster_and_the_counts(owner, built):
    cells = list(owner.execute(select(Cell).order_by(Cell.id)).scalars())
    gone = place(owner, "FAC-GONE", cells[0])
    place(owner, "FAC-HERE", cells[1])
    gone.released_at = NOW
    owner.flush()
    mine = [r["code"] for r in staff_views.roster(owner, NOW) if r["code"].startswith("FAC-")]
    assert mine == ["FAC-HERE"]
    assert staff_views.roster_page(owner, NOW, q="FAC-")["total"] == 1


# ---------------- recreation by floor ----------------
def blocks(owner, unit, day):
    return list(
        owner.execute(
            select(ScheduleBlock).where(ScheduleBlock.unit == unit, ScheduleBlock.day == day)
        ).scalars()
    )


def test_each_floor_gets_its_own_staggered_recreation_in_its_own_room(owner, built):
    day = NOW.date()
    schedule.ensure_day(owner, "H1-L1", day, NOW)
    rec_blocks = [b for b in blocks(owner, "H1-L1", day) if b.kind in ("indoor", "outdoor")]
    assert {b.floor for b in rec_blocks} == {1, 2, 3}
    cfg = get_current(owner, "facility").payload["rec"]
    for kind in ("indoor", "outdoor"):
        by_floor = {
            b.floor: b
            for b in rec_blocks
            if b.kind == kind
            and b.start == min(x.start for x in rec_blocks if x.floor == b.floor and x.kind == kind)
        }
        starts = [by_floor[f].start for f in (1, 2, 3)]
        assert len(set(starts)) == 3  # the floors are not let out together
        assert len({by_floor[f].rec_area_id for f in (1, 2, 3)}) == 3  # one room each
        assert all(b.capacity == cfg["room_capacity"] for b in by_floor.values())
    # programs and visits are shared by every floor
    assert {b.floor for b in blocks(owner, "H1-L1", day) if b.kind in ("program", "visit")} == {0}


def test_no_more_floors_are_out_at_once_than_the_line_allows(owner, built):
    day = NOW.date()
    cfg = dict(get_current(owner, "facility").payload)
    cfg["rec"] = {**cfg["rec"], "max_concurrent_out_per_line": 1, "stagger_minutes": 5}
    set_config(owner, SYSTEM, "facility", cfg, "test: one floor out at a time")
    schedule.ensure_day(owner, "H1-L2", day, NOW)
    all_blocks = blocks(owner, "H1-L2", day)
    yards = [(b.start, b.minutes) for b in all_blocks if b.kind == "outdoor"]
    assert schedule.max_concurrent_out(yards) <= 1  # one floor in the yards at a time
    assert {b.floor for b in all_blocks if b.kind == "indoor"} == {1, 2, 3}  # baseline untouched
    # staff cannot add a block that would break the limit...
    admin = SYSTEM
    with pytest.raises(schedule.ScheduleError) as e:
        schedule.add_block(
            owner,
            admin,
            "H1-L2",
            day,
            "outdoor",
            "10:30",
            60,
            10,
            None,
            None,
            "extra yard time",
            NOW,
        )
    assert e.value.code == "LINE_BUSY"
    # ...and day rooms are limited by how many day rooms there are, not by the yard limit
    schedule.add_block(
        owner, admin, "H1-L2", day, "indoor", "09:10", 60, 10, None, None, "extra day room", NOW
    )


def test_a_resident_only_sees_and_books_their_own_floors_blocks(owner, built, seeded):
    cells = list(owner.execute(select(Cell).order_by(Cell.id)).scalars())
    f1 = place(owner, "FAC-F1", next(c for c in cells if c.code.startswith("H1-L1-F1")))
    f2 = place(owner, "FAC-F2", next(c for c in cells if c.code.startswith("H1-L1-F2")))
    day = NOW.date()
    schedule.ensure_day(owner, "H1-L1", day, NOW)
    v1, v2 = rec.day_view(owner, f1.id, day, NOW), rec.day_view(owner, f2.id, day, NOW)
    indoor1 = [s for s in v1["slots"] if s["kind"] == "indoor"]
    indoor2 = [s for s in v2["slots"] if s["kind"] == "indoor"]
    assert indoor1 and indoor2
    assert {s["slot"] for s in indoor1}.isdisjoint({s["slot"] for s in indoor2})
    mine = indoor1[0]
    with pytest.raises(rec.RecDenied):
        rec.book(owner, f2.id, day, mine["slot"], NOW)  # floor 2 cannot take floor 1's block
    assert rec.book(owner, f1.id, day, mine["slot"], NOW).block_id == mine["block_id"]


def test_a_unit_that_is_not_a_line_keeps_the_plain_template(owner, built):
    made = schedule.ensure_day(owner, "A", NOW.date(), NOW)
    assert made == len(schedule.template(owner))
    assert {b.floor for b in blocks(owner, "A", NOW.date())} == {0}


def test_the_facility_config_is_validated_and_versioned(owner, seeded):
    bad = dict(get_current(owner, "facility").payload)
    bad["rec"] = {**bad["rec"], "max_concurrent_out_per_line": 99}
    with pytest.raises(ValueError):
        set_config(owner, SYSTEM, "facility", bad, "too many at once")
    ok = dict(get_current(owner, "facility").payload)
    ok["rec"] = {**ok["rec"], "room_capacity": 12}
    assert set_config(owner, SYSTEM, "facility", ok, "smaller rooms").version >= 2
