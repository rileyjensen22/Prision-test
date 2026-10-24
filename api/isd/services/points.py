"""Point events and earned-tier evaluation."""

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from isd.engine.config import EngineConfig
from isd.engine.tiers import TierDecision
from isd.engine.tiers import evaluate_tier as decide_tier
from isd.models import PointEvent, TierHistory
from isd.services.audit import SYSTEM, Actor, append_audit
from isd.services.entitlement_service import earned_tier, load_engine_config

STAFF_ENTERED_ROLES = ("officer", "supervisor", "admin")
# Infraction deductions only come from the sanction workflow, never entered directly.
RESERVED_KINDS = ("confirmed_minor_infraction", "confirmed_major_infraction")


def total_points(session: Session, resident_id: int, at_time: datetime) -> int:
    return (
        session.execute(
            select(func.coalesce(func.sum(PointEvent.points), 0)).where(
                PointEvent.resident_id == resident_id, PointEvent.created_at <= at_time
            )
        ).scalar()
        or 0
    )


def total_points_many(
    session: Session, resident_ids: list[int], at_time: datetime
) -> dict[int, int]:
    rows = session.execute(
        select(PointEvent.resident_id, func.sum(PointEvent.points))
        .where(PointEvent.resident_id.in_(resident_ids), PointEvent.created_at <= at_time)
        .group_by(PointEvent.resident_id)
    ).all()
    found = {rid: int(total or 0) for rid, total in rows}
    return {rid: found.get(rid, 0) for rid in resident_ids}


def record_points(
    session: Session,
    actor: Actor,
    resident_id: int,
    kind: str,
    points: int,
    source: str,
    now: datetime,
    reason: str | None = None,
    sanction_id: int | None = None,
) -> PointEvent:
    ev = PointEvent(
        resident_id=resident_id,
        kind=kind,
        points=points,
        source=source,
        reason=reason,
        created_by=actor.id,
        created_at=now,
        ref_sanction_id=sanction_id,
    )
    session.add(ev)
    session.flush()
    append_audit(
        session,
        actor,
        "point_event",
        "resident",
        resident_id,
        reason_code=kind.upper(),
        payload={"points": points, "event_id": ev.id, "sanction_id": sanction_id},
    )
    return ev


def add_point_event(
    session: Session,
    actor: Actor,
    resident_id: int,
    kind: str,
    now: datetime,
    reason: str | None = None,
    cfg: EngineConfig | None = None,
) -> PointEvent:
    cfg = cfg or load_engine_config(session)
    rule = cfg.point_events.get(kind)
    if rule is None or kind in RESERVED_KINDS:
        raise ValueError(f"cannot add point event of kind {kind!r}")
    if rule["source"] == "system" and actor.role != "system":
        raise PermissionError(f"{kind} is system-detected")
    if rule["source"] == "staff" and actor.role not in STAFF_ENTERED_ROLES:
        raise PermissionError(f"{actor.role} cannot enter {kind}")
    if rule.get("reason_required") and not (reason or "").strip():
        raise ValueError(f"{kind} requires a reason")
    weekly_max = rule.get("max_per_week")
    if weekly_max is not None:
        used = session.execute(
            select(func.count()).where(
                PointEvent.resident_id == resident_id,
                PointEvent.kind == kind,
                PointEvent.created_at > now - timedelta(days=7),
            )
        ).scalar()
        if used >= weekly_max:
            raise ValueError(f"{kind} limit of {weekly_max}/week reached")
    ev = record_points(
        session, actor, resident_id, kind, rule["points"], rule["source"], now, reason
    )
    evaluate_tier(session, resident_id, now, cfg)
    return ev


def last_drop_at(session: Session, resident_id: int) -> datetime | None:
    return session.execute(
        select(func.max(TierHistory.at)).where(
            TierHistory.resident_id == resident_id, TierHistory.to_tier < TierHistory.from_tier
        )
    ).scalar()


def evaluate_tier(
    session: Session, resident_id: int, now: datetime, cfg: EngineConfig | None = None
) -> TierDecision:
    """Apply promotion/demotion rules and record any change. Safe to call repeatedly."""
    cfg = cfg or load_engine_config(session)
    current = earned_tier(session, resident_id, now)
    points = total_points(session, resident_id, now)
    decision = decide_tier(current, points, cfg, last_drop_at(session, resident_id), now)
    if decision.tier != current:
        session.add(
            TierHistory(
                resident_id=resident_id,
                at=now,
                from_tier=current,
                to_tier=decision.tier,
                points=points,
            )
        )
        session.flush()
        append_audit(
            session,
            SYSTEM,
            "tier_change",
            "resident",
            resident_id,
            reason_code=f"TIER_{decision.direction.upper()}",
            payload={"from": current, "to": decision.tier, "points": points},
        )
    return decision
