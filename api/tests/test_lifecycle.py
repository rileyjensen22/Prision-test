"""Vacating, transferring and keep-separate: audited, nothing deleted, cells and devices freed."""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from isd.models import (
    AuditLog,
    Cell,
    Device,
    DeviceAssignment,
    KeepSeparate,
    MirrorSession,
    PointEvent,
    RecBooking,
    Resident,
    TrustLedger,
    VideoBooking,
    WelfareFlag,
)
from isd.services import commissary, keep_separate, lifecycle, points, staff_views
from isd.services.audit import SYSTEM
from tests.conftest import NOW


@pytest.fixture
def placed(owner, seeded):
    """A resident in a cell with a device, plus a second free cell and device."""
    tag = uuid.uuid4().hex[:6]
    cell = Cell(code=f"C-{tag}", unit="A")
    device = Device(code=f"D-{tag}")
    spare_cell, spare_device = Cell(code=f"S-{tag}", unit="B"), Device(code=f"SD-{tag}")
    r = Resident(code=f"R-{tag}", display_name="Synthetic")
    owner.add_all([cell, device, spare_cell, spare_device, r])
    owner.flush()
    owner.add(
        DeviceAssignment(
            device_id=device.id,
            cell_id=cell.id,
            resident_id=r.id,
            assigned_at=NOW - timedelta(days=3),
        )
    )
    owner.flush()
    return r, cell, device, spare_cell, spare_device


def actions(owner):
    return [a.action for a in owner.execute(select(AuditLog).order_by(AuditLog.seq)).scalars()]


def test_vacate_frees_the_cell_and_device_and_keeps_the_record(owner, make_staff, placed):
    r, cell, device, *_ = placed
    sup = make_staff("supervisor")
    points.record_points(owner, SYSTEM, r.id, "seed_adjustment", 40, "system", NOW)
    commissary.deposit(owner, SYSTEM, r.id, 500, "family", f"dep-{r.id}", NOW)
    owner.flush()
    before = len(actions(owner))
    p = lifecycle.vacate(owner, sup, r.id, "released at end of term", NOW)
    owner.flush()
    assert (p.cell_code, p.device_code) == (cell.code, device.code)
    row = owner.execute(
        select(DeviceAssignment).where(DeviceAssignment.resident_id == r.id)
    ).scalar()
    assert row.ended_at == NOW
    assert owner.get(Resident, r.id).released_at == NOW
    # the record and the money stay
    assert owner.execute(select(PointEvent).where(PointEvent.resident_id == r.id)).first()
    assert owner.execute(select(TrustLedger).where(TrustLedger.resident_id == r.id)).first()
    assert actions(owner)[before:] == ["resident_vacated"]
    # the cell and the device can be used again, and the roster no longer lists the resident
    again = lifecycle._find_place(owner, cell.code, device.code)
    assert again[0].code == cell.code
    assert r.code not in {x["code"] for x in staff_views.roster(owner, NOW)}


def test_vacate_closes_things_tied_to_the_cell(owner, make_staff, placed):
    r, cell, device, *_ = placed
    sup = make_staff("supervisor")
    contact_id = _contact(owner, r)
    owner.add(
        MirrorSession(
            staff_id=sup.id,
            resident_id=r.id,
            device_id=device.id,
            reason="check",
            started_at=NOW,
            last_seen_at=NOW,
        )
    )
    owner.add(
        VideoBooking(
            resident_id=r.id,
            contact_id=contact_id,
            starts_at=NOW + timedelta(days=1),
            minutes=10,
            created_at=NOW,
        )
    )
    owner.add(
        RecBooking(
            resident_id=r.id,
            day=(NOW + timedelta(days=1)).date(),
            slot="09:00",
            kind="indoor",
            created_at=NOW,
        )
    )
    owner.add(
        WelfareFlag(
            resident_id=r.id, flag_type="no_contact", severity="attention", detail={}, raised_at=NOW
        )
    )
    owner.flush()
    lifecycle.vacate(owner, sup, r.id, "released", NOW)
    owner.flush()
    assert (
        owner.execute(select(MirrorSession).where(MirrorSession.resident_id == r.id))
        .scalar()
        .ended_at
    )
    assert (
        owner.execute(select(VideoBooking).where(VideoBooking.resident_id == r.id)).scalar().status
        == "cancelled"
    )
    assert not owner.execute(select(RecBooking).where(RecBooking.resident_id == r.id)).first()
    assert (
        owner.execute(select(WelfareFlag).where(WelfareFlag.resident_id == r.id)).scalar().status
        == "cleared"
    )


def _contact(owner, r):
    from isd.models import Contact

    c = Contact(
        resident_id=r.id,
        name="Fam",
        type="family",
        phone_ref="555-0100",
        approved=True,
        status="approved",
    )
    owner.add(c)
    owner.flush()
    return c.id


def test_vacate_needs_a_reason_and_an_assignment(owner, make_staff, placed):
    r, *_ = placed
    sup = make_staff("supervisor")
    with pytest.raises(lifecycle.LifecycleError) as e:
        lifecycle.vacate(owner, sup, r.id, " ", NOW)
    assert e.value.code == "REASON_REQUIRED"
    lifecycle.vacate(owner, sup, r.id, "released", NOW)
    with pytest.raises(lifecycle.LifecycleError) as e:
        lifecycle.vacate(owner, sup, r.id, "again", NOW)
    assert e.value.code == "NOT_ASSIGNED"


def test_transfer_moves_the_assignment_and_audits_it(owner, make_staff, placed):
    r, cell, device, spare_cell, spare_device = placed
    sup = make_staff("supervisor")
    out = lifecycle.transfer(
        owner, sup, r.id, spare_cell.code, spare_device.code, "moved to unit B", NOW
    )
    owner.flush()
    rows = (
        owner.execute(
            select(DeviceAssignment)
            .where(DeviceAssignment.resident_id == r.id)
            .order_by(DeviceAssignment.id)
        )
        .scalars()
        .all()
    )
    assert [x.ended_at is not None for x in rows] == [True, False]
    assert rows[1].cell_id == spare_cell.id and rows[1].device_id == spare_device.id
    assert out["cell"] == spare_cell.code
    last = owner.execute(select(AuditLog).order_by(AuditLog.seq.desc()).limit(1)).scalar()
    assert last.action == "resident_transferred"
    assert last.payload["from_cell"] == cell.code and last.payload["to_cell"] == spare_cell.code


def test_transfer_to_an_occupied_place_is_refused(owner, make_staff, placed):
    r, cell, device, *_ = placed
    other = Resident(code=f"O-{uuid.uuid4().hex[:6]}", display_name="Synthetic")
    c2, d2 = Cell(code=f"C2-{uuid.uuid4().hex[:6]}"), Device(code=f"D2-{uuid.uuid4().hex[:6]}")
    owner.add_all([other, c2, d2])
    owner.flush()
    owner.add(DeviceAssignment(device_id=d2.id, cell_id=c2.id, resident_id=other.id))
    owner.flush()
    sup = make_staff("supervisor")
    with pytest.raises(lifecycle.IntakeError) as e:
        lifecycle.transfer(owner, sup, r.id, c2.code, d2.code, "move", NOW)
    assert e.value.code == "OCCUPIED"


def test_transfer_warns_when_a_kept_apart_resident_is_on_the_new_unit(owner, make_staff, placed):
    r, cell, device, spare_cell, spare_device = placed
    other = Resident(code=f"K-{uuid.uuid4().hex[:6]}", display_name="Synthetic")
    c2, d2 = (
        Cell(code=f"KC-{uuid.uuid4().hex[:6]}", unit="B"),
        Device(code=f"KD-{uuid.uuid4().hex[:6]}"),
    )
    owner.add_all([other, c2, d2])
    owner.flush()
    owner.add(DeviceAssignment(device_id=d2.id, cell_id=c2.id, resident_id=other.id))
    sup = make_staff("supervisor")
    keep_separate.add(owner, sup, r.code, other.code, "prior incident", NOW)
    out = lifecycle.transfer(owner, sup, r.id, spare_cell.code, spare_device.code, "move", NOW)
    assert out["keep_separate_on_new_unit"] == [other.code]


def test_keep_separate_add_and_end_are_audited_and_the_reason_stays_out_of_the_add_entry(
    owner, make_staff, placed
):
    r, *_ = placed
    other = Resident(code=f"P-{uuid.uuid4().hex[:6]}", display_name="Synthetic")
    owner.add(other)
    owner.flush()
    sup = make_staff("supervisor")
    row = keep_separate.add(owner, sup, r.code, other.code, "secret staff reason", NOW)
    assert row.resident_a_id < row.resident_b_id
    add_entry = owner.execute(select(AuditLog).order_by(AuditLog.seq.desc()).limit(1)).scalar()
    assert add_entry.action == "keep_separate_added" and "secret staff reason" not in str(
        add_entry.payload
    )
    with pytest.raises(keep_separate.SeparateError) as e:
        keep_separate.add(owner, sup, other.code, r.code, "again", NOW)
    assert e.value.code == "ALREADY_ENTERED"
    keep_separate.end(owner, sup, row.id, "resolved after review", NOW)
    assert owner.get(KeepSeparate, row.id).ended_at == NOW  # ended, never deleted
    with pytest.raises(keep_separate.SeparateError) as e:
        keep_separate.end(owner, sup, row.id, "twice", NOW)
    assert e.value.code == "ALREADY_ENDED"
    assert [x["id"] for x in keep_separate.list_open(owner)] == [
        x["id"] for x in keep_separate.list_open(owner) if x["ended_at"] is None
    ]


def test_routes_are_role_gated_and_work_end_to_end(
    client, staff_tokens, committed_config, kiosk, owner_engine
):
    rid, token, _ = kiosk()
    s = staff_tokens
    assert (
        client.post(
            f"/staff/residents/{rid}/vacate", json={"reason": "released"}, headers=s["officer"]
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/staff/residents/{rid}/vacate", json={"reason": "released"}, headers=s["auditor"]
        ).status_code
        == 403
    )
    r = client.post(
        f"/staff/residents/{rid}/vacate", json={"reason": "released"}, headers=s["supervisor"]
    )
    assert r.status_code == 200 and r.json()["freed_cell"]
    # the kiosk is now unassigned
    assert client.get("/device/view", headers={"X-Device-Token": token}).status_code == 409
    assert (
        client.post(
            f"/staff/residents/{rid}/vacate", json={"reason": "again"}, headers=s["supervisor"]
        ).status_code
        == 409
    )
    assert client.get("/staff/keep-separate", headers=s["auditor"]).status_code == 200
    assert client.get("/staff/keep-separate", headers=s["officer"]).status_code == 403
