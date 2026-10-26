"""Retention: periods come from compliance.yaml, unset keeps everything, and the append-only
tables (audit log, ledgers, points, sanctions...) are never touched."""

from datetime import timedelta

import pytest
from sqlalchemy import func, select, text

from isd.models import (
    AuditLog,
    CallRecord,
    Contact,
    Message,
    MessageFlag,
    QuizAttempt,
    ReadingLog,
    StaffRequest,
    VideoBooking,
)
from isd.services import commissary, points, retention
from isd.services.audit import SYSTEM
from isd.services.config_store import get_current, set_config
from tests.conftest import NOW

ALL_PERIODS = {rule.config_key: 30 for rule in retention.RULES}


def set_periods(owner, **periods):
    payload = dict(get_current(owner, "compliance").payload)
    for rule in retention.RULES:
        payload[rule.config_key] = None
    payload.update(periods)
    set_config(owner, SYSTEM, "compliance", payload, "test retention")


@pytest.fixture
def old_and_new(owner, seeded, make_resident):
    """One old and one recent row of each kind of record."""
    rid = make_resident()
    contact = Contact(
        resident_id=rid,
        name="Fam",
        type="family",
        phone_ref="555-0100",
        approved=True,
        status="approved",
    )
    owner.add(contact)
    owner.flush()
    old, new = NOW - timedelta(days=90), NOW - timedelta(days=2)
    msgs = []
    for when in (old, new):
        m = Message(
            resident_id=rid,
            contact_id=contact.id,
            direction="out",
            body="hello",
            privileged=False,
            monitored=True,
            created_at=when,
        )
        owner.add(m)
        owner.flush()
        owner.add(MessageFlag(message_id=m.id, rule_id="r", label="l", created_at=when))
        msgs.append(m)
        owner.add(
            StaffRequest(
                resident_id=rid,
                kind="staff",
                client_id=f"c-{when.timestamp()}-{rid}",
                created_at=when,
            )
        )
        owner.add(ReadingLog(resident_id=rid, item_id="x", at=when))
        owner.add(
            QuizAttempt(
                resident_id=rid, course_code="MONEY101", correct=1, total=2, passed=False, at=when
            )
        )
    calls = []
    for when in (old, new):
        c = CallRecord(
            resident_id=rid,
            contact_id=contact.id,
            contact_type="family",
            privileged=False,
            monitored=True,
            provider_ref=f"p-{when.timestamp()}-{rid}",
            started_at=when,
            max_seconds=900,
            duration_seconds=60,
            status="completed",
        )
        owner.add(c)
        owner.flush()
        calls.append(c)
    owner.add(
        VideoBooking(
            resident_id=rid,
            contact_id=contact.id,
            starts_at=old,
            minutes=10,
            call_id=calls[0].id,
            status="missed",
            created_at=old,
        )
    )
    owner.flush()
    return rid, msgs, calls


def count(owner, model):
    return owner.execute(select(func.count()).select_from(model)).scalar()


def test_unset_periods_keep_everything(owner, old_and_new):
    set_periods(owner)  # all null
    before = {
        m: count(owner, m) for m in (Message, CallRecord, StaffRequest, ReadingLog, QuizAttempt)
    }
    assert retention.run(owner, NOW) == {}
    assert before == {m: count(owner, m) for m in before}


def test_a_period_deletes_only_older_rows_of_that_kind(owner, old_and_new):
    rid, msgs, calls = old_and_new
    set_periods(owner, message_retention_days=30)
    out = retention.run(owner, NOW)
    assert out == {"message_retention_days": 1}
    left = owner.execute(select(Message.id).where(Message.resident_id == rid)).scalars().all()
    assert left == [msgs[1].id]
    assert (
        owner.execute(
            select(MessageFlag.message_id).where(MessageFlag.message_id == msgs[0].id)
        ).first()
        is None
    )
    assert count(owner, CallRecord) >= 2  # calls untouched


def test_calls_are_deleted_and_bookings_keep_their_row(owner, old_and_new):
    rid, msgs, calls = old_and_new
    set_periods(owner, call_metadata_retention_days=30)
    assert retention.run(owner, NOW) == {"call_metadata_retention_days": 1}
    booking = owner.execute(select(VideoBooking).where(VideoBooking.resident_id == rid)).scalar()
    assert booking.call_id is None and booking.status == "missed"
    assert owner.get(CallRecord, calls[1].id) is not None


def test_the_run_is_logged_with_counts_only_and_repeats_safely(owner, old_and_new):
    set_periods(owner, **ALL_PERIODS)
    retention.run(owner, NOW)
    entry = (
        owner.execute(
            select(AuditLog).where(AuditLog.action == "retention_run").order_by(AuditLog.seq.desc())
        )
        .scalars()
        .first()
    )
    assert entry.payload["deleted"]["message_retention_days"] == 1
    assert "hello" not in str(entry.payload)
    assert retention.run(owner, NOW) == {k: 0 for k in ALL_PERIODS}  # second run: nothing left


def test_invalid_periods_are_refused(owner, seeded):
    for bad in (0, -5, "30", True, 1.5):
        set_periods(owner, message_retention_days=bad)
        with pytest.raises(retention.RetentionConfigError):
            retention.run(owner, NOW)


def test_append_only_tables_are_untouched_whatever_the_periods(
    owner, seeded, make_resident, old_and_new
):
    """The audit log, ledgers, points, sanctions and decision records survive even the shortest
    retention periods: counts before and after match, apart from the run's own audit entry."""
    rid, *_ = old_and_new
    points.record_points(
        owner, SYSTEM, rid, "seed_adjustment", 25, "system", NOW - timedelta(days=400)
    )
    commissary.deposit(owner, SYSTEM, rid, 700, "fam", f"dep-{rid}", NOW - timedelta(days=400))
    owner.flush()
    tables = sorted(retention.PROTECTED)
    existing = {
        t
        for (t,) in owner.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        )
    }
    assert set(tables) <= existing, "PROTECTED names a table that does not exist"

    def snapshot():
        return {t: owner.execute(text(f'SELECT count(*) FROM "{t}"')).scalar() for t in tables}  # noqa: S608

    set_periods(owner, **{k: 1 for k in ALL_PERIODS})
    before = snapshot()
    retention.run(owner, NOW + timedelta(days=3650))  # ten years on
    after = snapshot()
    assert after.pop("audit_log") == before.pop("audit_log") + 1  # only the run's own entry
    assert after == before


def test_the_job_cannot_be_pointed_at_a_protected_table():
    assert not {rule.table for rule in retention.RULES} & retention.PROTECTED
    for table in ("audit_log", "trust_ledger", "earnings_ledger", "config_versions"):
        assert table in retention.PROTECTED
