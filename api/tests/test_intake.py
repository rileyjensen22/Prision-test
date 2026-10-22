"""Intake: one audited step that admits a resident, with offense, contact and separation parts."""

import uuid
from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from isd.models import (
    AuditLog,
    Cell,
    Contact,
    Device,
    DeviceAssignment,
    KeepSeparate,
    OffenseFlag,
    Resident,
)
from isd.services import intake as svc
from isd.services.entitlement_service import get_entitlements
from isd.services.intake import IntakeContact, IntakeError, IntakeRequest
from tests.conftest import NOW


@pytest.fixture
def place(owner):
    tag = uuid.uuid4().hex[:6]
    cell, device = Cell(code=f"C-{tag}"), Device(code=f"D-{tag}")
    owner.add_all([cell, device])
    owner.flush()
    return cell.code, device.code


def request(place, **over) -> IntakeRequest:
    base = dict(
        display_name="Synthetic Person",
        cell_code=place[0],
        device_code=place[1],
        reason="new admission",
    )
    return IntakeRequest(**{**base, **over})


def actions(owner):
    return [a.action for a in owner.execute(select(AuditLog).order_by(AuditLog.seq)).scalars()]


def test_intake_creates_everything_and_audits_each_part(owner, seeded, make_staff, place):
    actor = make_staff("supervisor")
    other = Resident(code="OTHER-1", display_name="Synthetic")
    owner.add(other)
    owner.flush()
    req = request(
        place,
        language="es",
        text_size="large",
        prior_returns=3,
        prior_returns_source="state records, synthetic",
        release_date=date(2027, 1, 1),
        offense_categories=["PLACEHOLDER_CATEGORY_A"],
        contacts=[
            IntakeContact("Pat Family", "family", "555-0142"),
            IntakeContact("Counsel", "attorney", "555-0143"),
        ],
        keep_separate=[("OTHER-1", "prior incident")],
    )
    before = len(actions(owner))
    r = svc.intake(owner, actor, req, NOW)

    assert (r.language, r.text_size, r.prior_returns, r.prior_returns_source) == (
        "es",
        "large",
        3,
        "state records, synthetic",
    )
    assert r.release_date == date(2027, 1, 1)
    assert owner.execute(
        select(DeviceAssignment).where(DeviceAssignment.resident_id == r.id)
    ).scalar()
    contacts = owner.execute(select(Contact).where(Contact.resident_id == r.id)).scalars().all()
    assert {c.type for c in contacts} == {"family", "attorney"}
    assert all(c.approved and c.status == "approved" for c in contacts)
    flag = owner.execute(select(OffenseFlag).where(OffenseFlag.resident_id == r.id)).scalar()
    assert flag.offense_category == "PLACEHOLDER_CATEGORY_A"
    assert (flag.next_review_at - flag.added_at).days == 90
    ks = owner.execute(select(KeepSeparate)).scalar()
    assert ks.resident_a_id < ks.resident_b_id
    assert svc.keep_separate_codes(owner, r.id) == ["OTHER-1"]

    new = actions(owner)[before:]
    for expected in (
        "resident_intake",
        "prior_returns_set",
        "release_date_set",
        "offense_category_added",
        "contact_added",
        "keep_separate_added",
        "device_assignment",
    ):
        assert expected in new
    assert new.count("contact_added") == 2


def test_the_offense_category_restricts_through_the_engine(owner, seeded, make_staff, place):
    r = svc.intake(
        owner,
        make_staff("admin"),
        request(place, offense_categories=["PLACEHOLDER_CATEGORY_A"]),
        NOW,
    )
    ent = get_entitlements(owner, r.id, NOW, seeded)
    assert not ent.features["video"].allowed
    assert any(x.source == "offense" for x in ent.features["video"].reasons)


def test_audit_entries_do_not_carry_names_or_numbers(owner, seeded, make_staff, place):
    svc.intake(
        owner,
        make_staff("supervisor"),
        request(place, contacts=[IntakeContact("Pat Family", "family", "555-0142")]),
        NOW,
    )
    log = " ".join(str(a.payload) for a in owner.execute(select(AuditLog)).scalars())
    assert "Pat Family" not in log and "555-0142" not in log and "Synthetic Person" not in log


@pytest.mark.parametrize(
    ("over", "code"),
    [
        ({"display_name": " "}, "BAD_NAME"),
        ({"prior_returns": 2}, "SOURCE_REQUIRED"),
        ({"prior_returns": -1}, "BAD_PRIOR_RETURNS"),
        ({"release_date": date(2020, 1, 1)}, "BAD_RELEASE_DATE"),
        ({"offense_categories": ["NOT_A_CATEGORY"]}, "UNKNOWN_OFFENSE_CATEGORY"),
        ({"offense_categories": ["PLACEHOLDER_CATEGORY_A"] * 2}, "DUPLICATE_OFFENSE_CATEGORY"),
        ({"contacts": [IntakeContact("Pat", "cousin", "555-0142")]}, "BAD_TYPE"),
        ({"contacts": [IntakeContact("Pat", "family", "abc")]}, "BAD_NUMBER"),
        (
            {
                "contacts": [
                    IntakeContact("A B", "family", "555-0142"),
                    IntakeContact("C D", "friend", "555-0142"),
                ]
            },
            "DUPLICATE",
        ),
        ({"keep_separate": [("NOPE", "reason here")]}, "NOT_FOUND"),
        ({"reason": "x"}, "REASON_REQUIRED"),
        ({"code": "a b"}, "BAD_CODE"),
    ],
)
def test_bad_intake_is_refused_and_nothing_is_written(owner, seeded, make_staff, place, over, code):
    actor = make_staff("supervisor")
    n_residents = len(owner.execute(select(Resident.id)).all())
    n_audit = len(actions(owner))
    with pytest.raises(IntakeError) as e:
        svc.intake(owner, actor, request(place, **over), NOW)
    assert e.value.code == code
    assert len(owner.execute(select(Resident.id)).all()) == n_residents
    assert len(actions(owner)) == n_audit


def test_an_occupied_cell_or_device_is_refused(owner, seeded, make_staff, place):
    actor = make_staff("supervisor")
    svc.intake(owner, actor, request(place), NOW)
    with pytest.raises(IntakeError) as e:
        svc.intake(owner, actor, request(place), NOW)
    assert e.value.code == "OCCUPIED"
    assert place[0] not in [c["code"] for c in svc.options(owner)["vacant_cells"]]
    assert place[1] not in svc.options(owner)["free_devices"]


def test_a_taken_code_is_refused(owner, seeded, make_staff, place):
    owner.add(Resident(code="TAKEN-1", display_name="Synthetic"))
    owner.flush()
    with pytest.raises(IntakeError) as e:
        svc.intake(owner, make_staff("admin"), request(place, code="TAKEN-1"), NOW)
    assert e.value.code == "CODE_TAKEN"


def test_keep_separate_pairs_are_stored_once_and_never_duplicated(owner, seeded, make_staff, place):
    a = Resident(code="KS-A", display_name="Synthetic")
    owner.add(a)
    owner.flush()
    owner.add(KeepSeparate(resident_a_id=a.id + 1, resident_b_id=a.id, reason="x"))
    with pytest.raises(DBAPIError):  # the pair must be stored smaller id first
        owner.flush()


# ---------------- over HTTP ----------------
@pytest.fixture
def free_place(owner_engine):
    tag = uuid.uuid4().hex[:6]
    with Session(owner_engine) as s, s.begin():
        s.add_all([Cell(code=f"HC-{tag}"), Device(code=f"HD-{tag}")])
    return f"HC-{tag}", f"HD-{tag}"


@pytest.mark.usefixtures("committed_config")
def test_intake_api_roles_and_flow(client, staff_tokens, free_place):
    body = {
        "display_name": "Synthetic Person",
        "cell_code": free_place[0],
        "device_code": free_place[1],
        "reason": "new admission",
        "offense_categories": ["PLACEHOLDER_CATEGORY_B"],
        "contacts": [{"name": "Pat Family", "type": "family", "phone": "555-0142"}],
    }
    assert (
        client.post("/staff/intake", json=body, headers=staff_tokens["officer"]).status_code == 403
    )
    assert (
        client.post("/staff/intake", json=body, headers=staff_tokens["auditor"]).status_code == 403
    )
    assert client.post("/staff/intake", json=body).status_code == 401
    ok = client.post("/staff/intake", json=body, headers=staff_tokens["supervisor"])
    assert ok.status_code == 201
    again = client.post("/staff/intake", json=body, headers=staff_tokens["supervisor"])
    assert again.status_code == 409 and again.json()["detail"]["code"] == "OCCUPIED"
    bad = client.post(
        "/staff/intake", json={**body, "extra": 1}, headers=staff_tokens["supervisor"]
    )
    assert bad.status_code == 422

    rid = ok.json()["resident_id"]
    ks = client.get(f"/staff/residents/{rid}/keep-separate", headers=staff_tokens["supervisor"])
    assert ks.json() == {"codes": []}
    assert (
        client.get(
            f"/staff/residents/{rid}/keep-separate", headers=staff_tokens["officer"]
        ).status_code
        == 403
    )


@pytest.mark.usefixtures("committed_config")
def test_intake_options_list_and_roles(client, staff_tokens):
    opts = client.get("/staff/intake/options", headers=staff_tokens["supervisor"]).json()
    assert {"vacant_cells", "free_devices", "offense_categories", "contact_types"} <= set(opts)
    assert client.get("/staff/intake/options", headers=staff_tokens["officer"]).status_code == 403
