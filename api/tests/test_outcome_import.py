"""Outcome CSV import: dry-run preview writes nothing, a bad row blocks everything, and a changed
answer is a correcting entry that points at the one it replaces (outcome rows are append-only)."""

import pytest
from sqlalchemy import func, select

from isd.analytics import service
from isd.analytics.service import OutcomeError
from isd.models import AuditLog, OutcomeImportBatch, OutcomeRecord, Resident
from isd.services.audit import Actor
from tests.conftest import NOW

ADMIN = Actor(None, "admin")
HEAD = "resident_code,window_months,outcome\n"


@pytest.fixture
def people(owner, seeded):
    out = []
    for i in range(3):
        r = Resident(code=f"IMP-{i}", display_name="Synthetic")
        owner.add(r)
        out.append(r)
    owner.flush()
    return out


def count(owner, model):
    return owner.execute(select(func.count()).select_from(model)).scalar()


def run(owner, text, dry_run):
    return service.import_outcomes(
        owner, ADMIN, text, "County record 2026-01", "jan", NOW, dry_run=dry_run
    )


def test_a_dry_run_previews_and_writes_nothing(owner, people):
    before = (count(owner, OutcomeRecord), count(owner, OutcomeImportBatch), count(owner, AuditLog))
    out = run(owner, HEAD + "IMP-0,12,no_return\nIMP-1,12,returned\n", dry_run=True)
    assert out["counts"] == {"new": 2, "correction": 0, "unchanged": 0}
    assert not out["imported"] and out["problems"] == []
    assert [p["action"] for p in out["preview"]] == ["new", "new"]
    after = (count(owner, OutcomeRecord), count(owner, OutcomeImportBatch), count(owner, AuditLog))
    assert before == after


def test_applying_adds_rows_in_one_batch_and_audits_it(owner, people):
    out = run(owner, HEAD + "IMP-0,12,no_return\nIMP-1,6,unknown\n", dry_run=False)
    assert out["imported"]
    rows = (
        owner.execute(select(OutcomeRecord).where(OutcomeRecord.batch_id == out["batch_id"]))
        .scalars()
        .all()
    )
    assert len(rows) == 2
    entry = (
        owner.execute(
            select(AuditLog)
            .where(AuditLog.action == "outcomes_imported")
            .order_by(AuditLog.seq.desc())
        )
        .scalars()
        .first()
    )
    assert entry is not None and entry.payload["new"] == 2


def test_a_different_answer_is_a_correction_and_a_repeat_is_skipped(owner, people):
    run(owner, HEAD + "IMP-0,12,no_return\nIMP-1,12,returned\n", dry_run=False)
    out = run(owner, HEAD + "IMP-0,12,returned\nIMP-1,12,returned\n", dry_run=False)
    assert out["counts"] == {"new": 0, "correction": 1, "unchanged": 1}
    rows = (
        owner.execute(
            select(OutcomeRecord)
            .where(OutcomeRecord.resident_id == people[0].id)
            .order_by(OutcomeRecord.id)
        )
        .scalars()
        .all()
    )
    assert [r.outcome for r in rows] == ["no_return", "returned"]
    assert rows[1].corrects_id == rows[0].id  # the old row is still there


def test_a_bad_row_blocks_the_whole_file(owner, people):
    text = HEAD + "IMP-0,12,no_return\nNOPE-9,12,returned\nIMP-1,7,returned\nIMP-2,6,maybe\n"
    before = count(owner, OutcomeRecord)
    out = run(owner, text, dry_run=False)
    assert not out["imported"]
    assert {(p["line"], p["code"]) for p in out["problems"]} == {
        (3, "NOT_FOUND"),
        (4, "BAD_WINDOW"),
        (5, "BAD_OUTCOME"),
    }
    assert count(owner, OutcomeRecord) == before


def test_the_file_and_source_are_checked(owner, people):
    with pytest.raises(OutcomeError) as e:
        run(owner, "name,value\nx,1\n", dry_run=True)
    assert e.value.code == "BAD_FILE"
    with pytest.raises(OutcomeError) as e:
        service.import_outcomes(owner, ADMIN, HEAD, " ", "x", NOW)
    assert e.value.code == "SOURCE_REQUIRED"


def test_the_same_person_twice_in_one_file_chains_correctly(owner, people):
    run(owner, HEAD + "IMP-2,24,returned\nIMP-2,24,no_return\n", dry_run=False)
    rows = (
        owner.execute(
            select(OutcomeRecord)
            .where(OutcomeRecord.resident_id == people[2].id)
            .order_by(OutcomeRecord.id)
        )
        .scalars()
        .all()
    )
    assert [r.outcome for r in rows] == ["returned", "no_return"]
    assert rows[0].corrects_id is None and rows[1].corrects_id == rows[0].id
