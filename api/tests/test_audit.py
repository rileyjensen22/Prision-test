import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, ProgrammingError

from isd.models import AuditLog
from isd.services.audit import SYSTEM, Actor, append_audit, verify_chain


def _add(session, n=3, **kw):
    return [
        append_audit(session, SYSTEM, "test_event", "thing", i, "TEST", payload={"i": i}, **kw)
        for i in range(n)
    ]


def test_chain_links_and_verifies(owner):
    rows = _add(owner, 3)
    assert rows[1].prev_hash == rows[0].hash
    assert rows[2].seq == rows[0].seq + 2
    assert verify_chain(owner).ok


def test_owner_cannot_update_or_delete_audit_rows(owner_engine):
    from sqlalchemy.orm import Session

    with Session(owner_engine) as s, s.begin():
        _add(s, 1)
    for stmt in (
        "UPDATE audit_log SET action = 'x'",
        "DELETE FROM audit_log",
        "TRUNCATE audit_log",
    ):
        with owner_engine.connect() as c, pytest.raises(DBAPIError, match="append-only"):
            c.execute(text(stmt))


def test_app_role_has_no_update_delete_grants(app_session):
    for stmt in ("UPDATE audit_log SET action = 'x'", "DELETE FROM audit_log"):
        with pytest.raises(ProgrammingError, match="permission denied"):
            app_session.execute(text(stmt))
        app_session.rollback()


def test_app_role_can_append(app_session):
    row = append_audit(app_session, Actor(1, "admin"), "x", "t", "1", "R")
    assert row.hash and verify_chain(app_session).ok


def test_verifier_detects_tampering(owner):
    """Disable the trigger inside a transaction (rolled back) to simulate a DB-level attack."""
    _add(owner, 3)
    owner.flush()
    target = owner.query(AuditLog).order_by(AuditLog.seq.desc()).offset(1).first()
    owner.execute(text("ALTER TABLE audit_log DISABLE TRIGGER audit_log_no_update_delete"))
    owner.execute(
        text("UPDATE audit_log SET action = 'tampered' WHERE seq = :s"), {"s": target.seq}
    )
    owner.expire_all()
    result = verify_chain(owner)
    assert not result.ok and result.first_bad_seq == target.seq
    owner.rollback()
    assert verify_chain(owner).ok


def test_verifier_detects_deleted_entry(owner):
    _add(owner, 3)
    owner.flush()
    mid = owner.query(AuditLog).order_by(AuditLog.seq.desc()).offset(1).first()
    owner.execute(text("ALTER TABLE audit_log DISABLE TRIGGER audit_log_no_update_delete"))
    owner.execute(text("UPDATE audit_log SET ref_seq = NULL"))  # keep FK clear
    owner.execute(text("DELETE FROM audit_log WHERE seq = :s"), {"s": mid.seq})
    owner.expire_all()
    result = verify_chain(owner)
    assert not result.ok
    assert "gap" in result.problem or "prev_hash" in result.problem
    owner.rollback()


def test_correction_references_original(owner):
    orig, *_ = _add(owner, 1)
    fix = append_audit(
        owner, Actor(1, "admin"), "correction", "audit_log", orig.seq, "FIX", ref_seq=orig.seq
    )
    assert fix.ref_seq == orig.seq and verify_chain(owner).ok
