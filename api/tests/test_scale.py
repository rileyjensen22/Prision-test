"""The staff roster must not slow down per resident, and must match the single-resident path."""

import uuid
from datetime import timedelta

from sqlalchemy import event

from isd.models import Cell, DeviceAssignment, OffenseFlag, Resident, Sanction, TierHistory
from isd.services import device_fleet as fleet
from isd.services import staff_views
from isd.services.entitlement_service import get_entitlements, get_entitlements_many
from tests.conftest import NOW


def populate(owner, make_staff, n):
    admin = make_staff("admin")
    ids = []
    for i in range(n):
        r = Resident(
            code=f"BULK-{uuid.uuid4().hex[:6]}", display_name="Synthetic", prior_returns=i % 5
        )
        owner.add(r)
        owner.flush()
        ids.append(r.id)
        cell = Cell(code=f"BC-{uuid.uuid4().hex[:6]}")
        dev = fleet.create_device(owner, admin, f"BD-{uuid.uuid4().hex[:6]}", NOW)
        owner.add(cell)
        owner.flush()
        owner.add(DeviceAssignment(device_id=dev.id, cell_id=cell.id, resident_id=r.id))
        if i % 2:
            owner.add(
                TierHistory(
                    resident_id=r.id,
                    at=NOW - timedelta(days=3),
                    from_tier=1,
                    to_tier=1 + i % 7,
                    points=i,
                )
            )
        if i % 3 == 0:
            owner.add(
                Sanction(
                    resident_id=r.id,
                    infraction_code="DISRUPT",
                    scope="communication",
                    reason_code="DISRUPT",
                    status="active",
                    starts_at=NOW - timedelta(hours=1),
                    ends_at=NOW + timedelta(hours=5),
                )
            )
        if i % 4 == 0:
            owner.add(
                OffenseFlag(
                    resident_id=r.id,
                    offense_category="SEX_OFFENSE",
                    added_at=NOW - timedelta(days=9),
                )
            )
        if i % 5 == 0:
            fleet.lock(owner, admin, dev.code, 2, "checking", NOW - timedelta(minutes=10))
    owner.flush()
    return ids


def test_the_bulk_path_gives_exactly_the_single_path_answers(owner, seeded, make_staff):
    ids = populate(owner, make_staff, 14)
    many = get_entitlements_many(owner, ids, NOW, seeded)
    for rid in ids:
        assert many[rid] == get_entitlements(owner, rid, NOW, seeded)
    assert any(not e.features["calls"].allowed for e in many.values())  # the data was not trivial


def test_roster_query_count_does_not_grow_with_residents(owner, seeded, make_staff):
    counted = {"n": 0}
    engine = owner.get_bind()

    def count(*_a, **_k):
        counted["n"] += 1

    populate(owner, make_staff, 4)
    event.listen(engine, "before_cursor_execute", count)
    try:
        staff_views.roster(owner, NOW)
        small = counted["n"]
        populate(owner, make_staff, 30)
        counted["n"] = 0
        rows = staff_views.roster(owner, NOW)
        large = counted["n"]
    finally:
        event.remove(engine, "before_cursor_execute", count)
    assert len(rows) >= 34
    assert large == small  # 34 residents cost the same queries as 4


def test_roster_rows_match_the_single_resident_numbers(owner, seeded, make_staff):
    ids = populate(owner, make_staff, 9)
    rows = {r["resident_id"]: r for r in staff_views.roster(owner, NOW)}
    for rid in ids:
        ent = get_entitlements(owner, rid, NOW, seeded)
        assert rows[rid]["tier"] == {
            "earned": ent.earned_tier,
            "ceiling": ent.ceiling_tier,
            "effective": ent.effective_tier,
        }
    assert any(rows[rid]["active_sanctions"] for rid in ids)
