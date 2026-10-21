"""Phase 7 exit criteria: the public export has no names; job opt-out creates no events."""

import csv
import io
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from isd.engine.authority import Evidence
from isd.engine.public_log import RECORD_FIELDS
from isd.models import (
    AuditLog,
    Cell,
    Contact,
    Device,
    DeviceAssignment,
    JobEnrollment,
    PointEvent,
    Resident,
    Sanction,
    Staff,
    TierHistory,
)
from isd.services import jobs, points, sanctions
from isd.services.audit import SYSTEM, Actor, verify_chain
from isd.services.config_store import get_current, set_config
from isd.services.entitlement_service import get_entitlements
from isd.services.public_log import PublicLogDisabled, export
from tests.conftest import NOW

SALT = "unit-test-salt"
SECRETS = [  # strings that must never appear in anything published
    "Zebediah Quillfeather",
    "Quillfeather",
    "RES-ZQ-0001",
    "officer_zebadee",
    "sup_zebadee",
    "secret-cam-ref-123",
    "lied to staff",
    "CELL-9Z",
    "DEV-9Z",
    "Counsel Zebadee",
    "555-0199",
]


@pytest.fixture(scope="module")
def pub_engine():
    """An empty database of its own, so exact counts are not disturbed by other tests' data."""
    from tests.conftest import make_database

    url = make_database("isd_pubtest")
    return create_engine(url)


@pytest.fixture
def pub(pub_engine):
    from isd.config_loader import load_config

    with Session(pub_engine) as s:
        for name, payload in load_config().items():
            set_config(s, SYSTEM, name, payload, "test seed")
        yield s
        s.rollback()


def enable_public_log(owner):
    cur = dict(get_current(owner, "compliance").payload)
    set_config(
        owner, SYSTEM, "compliance", {**cur, "public_log_enabled": True}, "test: enable public log"
    )


@pytest.fixture
def story(pub):
    owner = pub
    """Residents, staff and sanctions that are full of identifying details."""

    def staff(username, role):
        st = Staff(username=username, role=role, password_hash="x")
        owner.add(st)
        owner.flush()
        return Actor(st.id, role)

    officer, sup, other_sup = (
        staff("officer_zebadee", "officer"),
        staff("sup_zebadee", "supervisor"),
        staff("other_sup", "supervisor"),
    )
    colleague = staff("colleague_zebadee", "officer")
    res = Resident(code="RES-ZQ-0001", display_name="Zebediah Quillfeather")
    cell, dev = Cell(code="CELL-9Z"), Device(code="DEV-9Z")
    owner.add_all([res, cell, dev])
    owner.flush()
    owner.add(DeviceAssignment(device_id=dev.id, cell_id=cell.id, resident_id=res.id))
    owner.add(
        Contact(resident_id=res.id, name="Counsel Zebadee", type="attorney", phone_ref="555-0199")
    )
    owner.flush()

    made = []
    for i in range(4):  # minor, immediate, by an officer
        made.append(
            sanctions.issue_sanction(
                owner, officer, res.id, "DISRUPT", NOW - timedelta(days=30 + 8 * i)
            )
        )
    ev = Evidence("second_staff_report", colleague.id, "secret-cam-ref-123")
    big = sanctions.issue_sanction(owner, officer, res.id, "CAM_BLOCK", NOW - timedelta(days=2), ev)
    sanctions.confirm_sanction(owner, sup, big.id, NOW - timedelta(days=2))
    appeal = sanctions.file_appeal(owner, big.id, NOW - timedelta(days=1))
    sanctions.review_appeal(
        owner,
        other_sup,
        appeal.id,
        "overturned",
        "Quillfeather lied to staff",
        NOW - timedelta(hours=5),
    )
    rejected = sanctions.issue_sanction(
        owner,
        sup,
        res.id,
        "DEVICE_DAMAGE",
        NOW - timedelta(days=1),
        Evidence("second_staff_report", colleague.id),
    )
    sanctions.reject_sanction(owner, other_sup, rejected.id, "Quillfeather lied to staff", NOW)
    return res


def read_all(out: Path) -> str:
    return "\n".join(p.read_text() for p in sorted(out.iterdir()))


# ======================= public log: no names =======================
def test_export_is_off_by_default_and_writes_nothing(pub, tmp_path):
    owner = pub
    assert get_current(owner, "compliance").payload["public_log_enabled"] is False
    with pytest.raises(PublicLogDisabled):
        export(owner, NOW, SALT, tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_export_contains_no_names_ids_staff_or_free_text(pub, story, tmp_path):
    owner = pub
    enable_public_log(owner)
    out = tmp_path / "pub"
    result = export(owner, NOW, SALT, out)
    assert result["records"] == 6
    everything = read_all(out).lower()
    for secret in SECRETS:
        assert secret.lower() not in everything, f"{secret!r} leaked into the public export"
    assert str(story.id) not in re.findall(
        r'"resident": "([^"]+)"', everything
    )  # never the internal id

    records = json.loads((out / "records.json").read_text())["records"]
    for r in records:
        assert set(r) == set(RECORD_FIELDS)  # nothing but the allow-listed fields
        assert re.fullmatch(r"R-[0-9a-f]{12}", r["resident"]) and re.fullmatch(
            r"E-[0-9a-f]{12}", r["event"]
        )
        assert datetime.fromisoformat(r["week"]).weekday() == 0  # a Monday, not an exact day
        assert r["issued_by_role"] in {"officer", "supervisor", "system"}
    assert len({r["resident"] for r in records}) == 1  # one person, one stable pseudonym

    rows = list(csv.DictReader(io.StringIO((out / "records.csv").read_text())))
    assert [list(r) for r in rows][0] == list(RECORD_FIELDS)
    assert all(re.fullmatch(r"R-[0-9a-f]{12}", r["resident"]) for r in rows)


def test_outcomes_and_per_role_totals(pub, story, tmp_path):
    owner = pub
    enable_public_log(owner)
    out = tmp_path / "pub"
    export(owner, NOW, SALT, out)
    records = json.loads((out / "records.json").read_text())["records"]
    by_code = {}
    for r in records:
        by_code.setdefault(r["code"], []).append(r)
    assert {r["outcome"] for r in by_code["DISRUPT"]} == {"ended"}
    (cam,) = by_code["CAM_BLOCK"]
    assert (cam["outcome"], cam["appeal"], cam["confirmed_by_role"]) == (
        "overturned",
        "overturned",
        "supervisor",
    )
    assert 0 < cam["hours_served"] < 48
    (dmg,) = by_code["DEVICE_DAMAGE"]
    assert (dmg["outcome"], dmg["hours_served"], dmg["issued_by_role"]) == (
        "rejected",
        0,
        "supervisor",
    )
    summary = json.loads((out / "summary.json").read_text())
    assert summary["by_issuing_role"]["officer"]["issued"] == 5
    assert (
        summary["by_issuing_role"]["supervisor"]["issued"] == "<3"
    )  # a small group is not published
    assert summary["by_code"]["DEVICE_DAMAGE"] == "<3"


def test_pseudonyms_depend_on_the_salt_and_the_page_is_static(pub, story, tmp_path):
    owner = pub
    enable_public_log(owner)
    export(owner, NOW, SALT, tmp_path / "a")
    export(owner, NOW, SALT, tmp_path / "b")
    export(owner, NOW, "another-salt", tmp_path / "c")
    first = lambda d: json.loads((d / "records.json").read_text())["records"][0]["resident"]  # noqa: E731
    assert first(tmp_path / "a") == first(tmp_path / "b") != first(tmp_path / "c")
    page = (tmp_path / "a" / "index.html").read_text()
    assert "<script" not in page.lower() and "http://" not in page and "https://" not in page
    assert "default-src 'none'" in page and "Sanctions transparency report" in page


def test_manifest_matches_files_and_the_export_is_audited_without_content(pub, story, tmp_path):
    owner = pub
    import hashlib

    enable_public_log(owner)
    out = tmp_path / "pub"
    export(owner, NOW, SALT, out)
    manifest = json.loads((out / "manifest.json").read_text())["sha256"]
    for name, digest in manifest.items():
        assert hashlib.sha256((out / name).read_bytes()).hexdigest() == digest
    entry = (
        owner.execute(select(AuditLog).where(AuditLog.action == "public_log_export"))
        .scalars()
        .one()
    )
    assert set(entry.payload) == {"records", "manifest_sha256"}
    assert verify_chain(owner).ok


def test_script_refuses_while_the_operator_toggle_is_off(tmp_path, owner_engine, committed_config):
    from tests.conftest import OWNER_URL

    out = tmp_path / "script-out"
    api_dir = Path(__file__).resolve().parents[1]
    res = subprocess.run(
        [
            sys.executable,
            str(api_dir.parent / "scripts" / "export-public-log.py"),
            "--out",
            str(out),
        ],
        env={
            **__import__("os").environ,
            "MIGRATION_DATABASE_URL": OWNER_URL.render_as_string(hide_password=False),
        },
        capture_output=True,
        text=True,
        cwd=api_dir,
    )
    assert res.returncode == 2 and "not exported" in res.stdout
    assert not out.exists()


# ======================= jobs: voluntary, no consequences =======================
def counts(owner, rid):
    return (
        owner.execute(
            select(func.count()).select_from(PointEvent).where(PointEvent.resident_id == rid)
        ).scalar(),
        owner.execute(
            select(func.count()).select_from(Sanction).where(Sanction.resident_id == rid)
        ).scalar(),
        owner.execute(
            select(func.count()).select_from(TierHistory).where(TierHistory.resident_id == rid)
        ).scalar(),
        owner.execute(select(func.count()).select_from(AuditLog)).scalar(),
    )


def test_declining_joining_and_leaving_create_no_points_sanctions_or_tier_events(
    owner, seeded, reference_data, make_resident
):
    rid = make_resident()
    points.record_points(
        owner, SYSTEM, rid, "seed_adjustment", 120, "system", NOW - timedelta(days=1)
    )
    points.evaluate_tier(owner, rid, NOW)
    listing = jobs.list_listings(owner, rid)[0]
    before = counts(owner, rid)
    ent_before = get_entitlements(owner, rid, NOW)

    # declining = simply never joining: looking at the list changes nothing
    jobs.list_listings(owner, rid)
    assert counts(owner, rid) == before

    jobs.opt_in(owner, rid, listing["id"], NOW)
    assert get_entitlements(owner, rid, NOW) == ent_before  # working changes no entitlement
    jobs.leave(owner, rid, listing["id"], NOW + timedelta(hours=1))
    assert counts(owner, rid) == before  # leaving creates nothing either
    later = get_entitlements(owner, rid, NOW + timedelta(hours=1))
    assert (
        later.features == ent_before.features and later.effective_tier == ent_before.effective_tier
    )


def test_joined_and_not_joined_residents_have_identical_entitlements(
    owner, seeded, reference_data, make_resident
):
    a, b = make_resident(), make_resident()
    for rid in (a, b):
        points.record_points(
            owner, SYSTEM, rid, "seed_adjustment", 700, "system", NOW - timedelta(days=1)
        )
        points.evaluate_tier(owner, rid, NOW)
    jobs.opt_in(owner, a, jobs.list_listings(owner, a)[0]["id"], NOW)
    ea, eb = get_entitlements(owner, a, NOW), get_entitlements(owner, b, NOW)
    assert ea.features == eb.features and ea.effective_tier == eb.effective_tier


def test_nothing_that_decides_entitlements_knows_about_jobs():
    root = Path(__file__).resolve().parents[1] / "isd"
    for path in [
        *(root / "engine").glob("*.py"),
        root / "services" / "entitlement_service.py",
        root / "services" / "points.py",
        root / "services" / "sanctions.py",
    ]:
        text = path.read_text().lower()
        assert "job" not in text, f"{path.name} mentions jobs"
    jobs_src = (root / "services" / "jobs.py").read_text()
    for forbidden in ("points", "sanctions", "entitlement", "tier"):
        assert not re.search(rf"^\s*(from|import)\s+.*{forbidden}", jobs_src, re.M), (
            f"jobs.py imports {forbidden}"
        )


def test_one_active_enrollment_and_rejoining(owner, seeded, reference_data, make_resident):
    rid = make_resident()
    job = jobs.list_listings(owner, rid)[0]["id"]
    jobs.opt_in(owner, rid, job, NOW)
    with pytest.raises(jobs.JobError) as e:
        jobs.opt_in(owner, rid, job, NOW)
    assert e.value.code == "ALREADY_JOINED"
    jobs.leave(owner, rid, job, NOW)
    with pytest.raises(jobs.JobError) as e:
        jobs.leave(owner, rid, job, NOW)
    assert e.value.code == "NOT_JOINED"
    jobs.opt_in(owner, rid, job, NOW + timedelta(days=1))  # free to come back
    assert (
        owner.execute(
            select(func.count()).select_from(JobEnrollment).where(JobEnrollment.resident_id == rid)
        ).scalar()
        == 2
    )


def test_job_task_types_and_pay_split_are_restricted(owner, seeded, reference_data):
    admin = Actor(None, "admin")
    with pytest.raises(jobs.JobError) as e:
        jobs.create_listing(
            owner,
            admin,
            "CALLCTR",
            "Customer support",
            "customer_support",
            "handles customers' data",
            NOW,
        )
    assert e.value.code == "BAD_TASK_TYPE"
    assert jobs.create_listing(
        owner, admin, "LABEL", "Label shapes", "labeling_non_personal", "Sort images of shapes", NOW
    ).active
    cfg = dict(get_current(owner, "jobs").payload)
    assert sum(cfg["pay_split"].values()) == 100
    with pytest.raises(ValueError):
        set_config(
            owner,
            admin,
            "jobs",
            {**cfg, "pay_split": {"resident_pct": 50, "facility_pct": 30, "deductions_pct": 10}},
            "bad split",
        )
