"""Sanction and appeal workflow. Authority rules live in isd.engine.authority."""

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from isd.engine.authority import (
    AuthorityError,
    Evidence,
    check_appeal_review,
    check_confirm,
    decide_issue,
)
from isd.engine.config import EngineConfig
from isd.models import Appeal, PointEvent, Sanction, Staff
from isd.services.audit import Actor, append_audit
from isd.services.entitlement_service import load_engine_config
from isd.services.points import evaluate_tier, record_points


def _get_for_update(session: Session, sanction_id: int) -> Sanction:
    row = session.execute(
        select(Sanction).where(Sanction.id == sanction_id).with_for_update()
    ).scalar()
    if row is None:
        raise LookupError(f"sanction {sanction_id} not found")
    return row


def _immediate_count(session: Session, officer_id: int | None, now: datetime) -> int:
    if officer_id is None:
        return 0
    return session.execute(
        select(func.count()).where(
            Sanction.issued_by == officer_id,
            Sanction.applied_immediately.is_(True),
            Sanction.issued_at > now - timedelta(days=7),
            Sanction.issued_at <= now,
        )
    ).scalar()


def _activate(session: Session, s: Sanction, cfg: EngineConfig, actor: Actor, now: datetime):
    rule = cfg.infractions[s.infraction_code]
    s.status = "active"
    s.starts_at = now
    s.ends_at = now + timedelta(hours=rule.duration_hours)
    # Points and sanctions are separate: the sanction locks features; this is the point event.
    kind = f"confirmed_{rule.severity}_infraction"
    record_points(
        session,
        actor,
        s.resident_id,
        kind,
        cfg.point_events[kind]["points"],
        "staff",
        now,
        reason=s.infraction_code,
        sanction_id=s.id,
    )
    evaluate_tier(session, s.resident_id, now, cfg)


def issue_sanction(
    session: Session,
    actor: Actor,
    resident_id: int,
    infraction_code: str,
    now: datetime,
    evidence: Evidence | None = None,
    cfg: EngineConfig | None = None,
) -> Sanction:
    cfg = cfg or load_engine_config(session)
    rule = cfg.infractions.get(infraction_code)
    if rule is None:
        raise AuthorityError("UNKNOWN_CODE", f"unknown infraction code {infraction_code!r}")
    if evidence is not None and evidence.reporter_id is not None:
        reporter = session.get(Staff, evidence.reporter_id)
        if reporter is None or not reporter.active:
            raise AuthorityError("EVIDENCE_REQUIRED", "reporter must be an active staff member")
    decision = decide_issue(
        rule, actor.role, actor.id, evidence, _immediate_count(session, actor.id, now), cfg
    )
    s = Sanction(
        resident_id=resident_id,
        infraction_code=rule.code,
        scope=rule.scope,
        reason_code=rule.code,
        status="pending",
        issued_by=actor.id,
        issued_at=now,
        evidence_type=evidence.type if evidence else None,
        evidence_ref=evidence.ref if evidence else None,
        evidence_reporter_id=evidence.reporter_id if evidence else None,
        applied_immediately=decision.applied_immediately,
    )
    session.add(s)
    session.flush()
    if decision.status == "active":
        _activate(session, s, cfg, actor, now)
    append_audit(
        session,
        actor,
        "sanction_issued",
        "resident",
        resident_id,
        reason_code=rule.code,
        payload={"sanction_id": s.id, "status": s.status, "note": decision.note},
    )
    return s


def confirm_sanction(
    session: Session, actor: Actor, sanction_id: int, now: datetime, cfg: EngineConfig | None = None
) -> Sanction:
    cfg = cfg or load_engine_config(session)
    s = _get_for_update(session, sanction_id)
    check_confirm(s.status, s.issued_by, actor.role, actor.id)
    s.confirmed_by, s.confirmed_at = actor.id, now
    _activate(session, s, cfg, actor, now)
    append_audit(
        session,
        actor,
        "sanction_confirmed",
        "resident",
        s.resident_id,
        reason_code=s.reason_code,
        payload={"sanction_id": s.id},
    )
    return s


def reject_sanction(
    session: Session, actor: Actor, sanction_id: int, note: str, now: datetime
) -> Sanction:
    s = _get_for_update(session, sanction_id)
    check_confirm(s.status, s.issued_by, actor.role, actor.id)  # same bar as confirming
    s.status, s.confirmed_by, s.confirmed_at = "rejected", actor.id, now
    append_audit(
        session,
        actor,
        "sanction_rejected",
        "resident",
        s.resident_id,
        reason_code=s.reason_code,
        payload={"sanction_id": s.id, "note": note},
    )
    return s


def file_appeal(
    session: Session, sanction_id: int, now: datetime, cfg: EngineConfig | None = None
) -> Appeal:
    """Filed from the resident device (baseline feature), so no staff actor."""
    cfg = cfg or load_engine_config(session)
    s = _get_for_update(session, sanction_id)
    if s.status != "active":
        raise AuthorityError("NOT_APPEALABLE", "only active sanctions can be appealed")
    already = session.execute(
        select(func.count()).where(Appeal.sanction_id == s.id, Appeal.status == "open")
    ).scalar()
    if already:
        raise AuthorityError("DUPLICATE_APPEAL", "an appeal is already open")
    appeal = Appeal(
        sanction_id=s.id,
        filed_at=now,
        due_at=now + timedelta(hours=cfg.appeal_review_hours),
        status="open",
    )
    session.add(appeal)
    session.flush()
    append_audit(
        session,
        Actor(None, "resident"),
        "appeal_filed",
        "resident",
        s.resident_id,
        reason_code=s.reason_code,
        payload={"appeal_id": appeal.id, "sanction_id": s.id},
    )
    return appeal


def review_appeal(
    session: Session,
    actor: Actor,
    appeal_id: int,
    outcome: str,
    note: str,
    now: datetime,
    cfg: EngineConfig | None = None,
) -> Appeal:
    if outcome not in ("upheld", "overturned"):
        raise ValueError("outcome must be upheld or overturned")
    cfg = cfg or load_engine_config(session)
    appeal = session.execute(
        select(Appeal).where(Appeal.id == appeal_id).with_for_update()
    ).scalar()
    if appeal is None or appeal.status != "open":
        raise AuthorityError("NOT_OPEN", "appeal not found or already decided")
    s = _get_for_update(session, appeal.sanction_id)
    check_appeal_review(s.issued_by, actor.role, actor.id)
    appeal.status, appeal.reviewer_id, appeal.reviewed_at = outcome, actor.id, now
    appeal.outcome_note = note
    if outcome == "overturned":
        s.status, s.overturned_at = "overturned", now
        _reverse_points(session, actor, s, now)
        evaluate_tier(session, s.resident_id, now, cfg)
    append_audit(
        session,
        actor,
        "appeal_reviewed",
        "resident",
        s.resident_id,
        reason_code=outcome.upper(),
        payload={"appeal_id": appeal.id, "sanction_id": s.id, "note": note},
    )
    return appeal


def _reverse_points(session: Session, actor: Actor, s: Sanction, now: datetime) -> None:
    deducted = session.execute(
        select(func.coalesce(func.sum(PointEvent.points), 0)).where(
            PointEvent.ref_sanction_id == s.id
        )
    ).scalar()
    if deducted:
        record_points(
            session,
            actor,
            s.resident_id,
            "infraction_reversal",
            -deducted,
            "staff",
            now,
            reason="appeal overturned",
            sanction_id=s.id,
        )


def overdue_appeals(session: Session, now: datetime) -> list[Appeal]:
    return list(
        session.execute(
            select(Appeal).where(Appeal.status == "open", Appeal.due_at < now)
        ).scalars()
    )
