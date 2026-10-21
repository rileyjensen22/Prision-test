"""Read models for the staff dashboard. Everything here is read-only."""

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from isd.engine.authority import needs_supervisor
from isd.engine.outliers import StaffStats, find_outliers
from isd.models import (
    Appeal,
    AuditLog,
    Cell,
    Device,
    DeviceAssignment,
    PointEvent,
    Resident,
    Sanction,
    Staff,
    TierHistory,
)
from isd.services import welfare
from isd.services.config_store import get_current
from isd.services.entitlement_service import get_entitlements, load_engine_config
from isd.services.points import total_points

DEFAULT_OUTLIER = {"window_days": 30, "z_threshold": 2.0, "min_peers": 3, "min_count": 3}
EVENT_ACTIONS = (
    "sanction_issued",
    "sanction_confirmed",
    "sanction_rejected",
    "appeal_filed",
    "appeal_reviewed",
    "tier_change",
    "resident_settings_change",
    "device_assignment",
    "config_change",
    "deposit",
)


def _names(session: Session, ids: set[int | None]) -> dict[int, str]:
    ids = {i for i in ids if i is not None}
    if not ids:
        return {}
    rows = session.execute(select(Staff.id, Staff.username).where(Staff.id.in_(ids)))
    return {i: u for i, u in rows}


def _ref(names: dict[int, str], staff_id: int | None) -> dict[str, Any] | None:
    return None if staff_id is None else {"id": staff_id, "username": names.get(staff_id, "?")}


def colleagues(session: Session) -> list[dict]:
    rows = session.execute(
        select(Staff).where(Staff.active.is_(True)).order_by(Staff.username)
    ).scalars()
    return [{"id": s.id, "username": s.username, "role": s.role} for s in rows]


def roster(session: Session, now: datetime) -> list[dict]:
    cfg = load_engine_config(session)
    offline_after = timedelta(
        minutes=int(get_current(session, "compliance").payload["offline_alert_minutes"])
    )
    out = []
    residents = session.execute(select(Resident).order_by(Resident.code)).scalars().all()
    for r in residents:
        asg = session.execute(
            select(DeviceAssignment, Device, Cell)
            .join(Device, Device.id == DeviceAssignment.device_id)
            .join(Cell, Cell.id == DeviceAssignment.cell_id)
            .where(DeviceAssignment.resident_id == r.id, DeviceAssignment.ended_at.is_(None))
        ).first()
        ent = get_entitlements(session, r.id, now, cfg)
        active = session.execute(
            select(Sanction).where(
                Sanction.resident_id == r.id, Sanction.status == "active", Sanction.ends_at > now
            )
        ).scalars()
        pending = session.execute(
            select(func.count()).where(Sanction.resident_id == r.id, Sanction.status == "pending")
        ).scalar()
        open_appeals = session.execute(
            select(func.count())
            .select_from(Appeal)
            .join(Sanction, Sanction.id == Appeal.sanction_id)
            .where(Sanction.resident_id == r.id, Appeal.status == "open")
        ).scalar()
        last_sync = asg[1].last_sync_at if asg else None
        out.append(
            {
                "resident_id": r.id,
                "code": r.code,
                "display_name": r.display_name,
                "cell": asg[2].code if asg else None,
                "device": asg[1].code if asg else None,
                "last_sync_at": last_sync.isoformat() if last_sync else None,
                "offline": bool(asg) and (last_sync is None or now - last_sync > offline_after),
                "tier": {
                    "earned": ent.earned_tier,
                    "ceiling": ent.ceiling_tier,
                    "effective": ent.effective_tier,
                },
                "points": total_points(session, r.id, now),
                "active_sanctions": [
                    {"id": s.id, "code": s.reason_code, "ends_at": s.ends_at.isoformat()}
                    for s in active
                ],
                "pending_sanctions": pending,
                "open_appeals": open_appeals,
            }
        )
    return out


def resident_detail(session: Session, resident_id: int, now: datetime) -> dict | None:
    r = session.get(Resident, resident_id)
    if r is None:
        return None
    sanctions = (
        session.execute(
            select(Sanction).where(Sanction.resident_id == r.id).order_by(Sanction.id.desc())
        )
        .scalars()
        .all()
    )
    names = _names(session, {x.issued_by for x in sanctions} | {x.confirmed_by for x in sanctions})
    asg = session.execute(
        select(Device.code, Cell.code)
        .select_from(DeviceAssignment)
        .join(Device, Device.id == DeviceAssignment.device_id)
        .join(Cell, Cell.id == DeviceAssignment.cell_id)
        .where(DeviceAssignment.resident_id == r.id, DeviceAssignment.ended_at.is_(None))
    ).first()
    ent = get_entitlements(session, r.id, now)
    return {
        "resident_id": r.id,
        "code": r.code,
        "display_name": r.display_name,
        "settings": {
            "language": r.language,
            "text_size": r.text_size,
            "reading_level": r.reading_level,
            "captions": r.captions,
        },
        "prior_returns": r.prior_returns,
        "device": asg[0] if asg else None,
        "cell": asg[1] if asg else None,
        "tier": {
            "earned": ent.earned_tier,
            "ceiling": ent.ceiling_tier,
            "effective": ent.effective_tier,
        },
        "points": total_points(session, r.id, now),
        "sanctions": [
            {
                "id": s.id,
                "code": s.infraction_code,
                "status": s.status,
                "issued_at": s.issued_at.isoformat(),
                "issued_by": _ref(names, s.issued_by),
                "confirmed_by": _ref(names, s.confirmed_by),
                "starts_at": s.starts_at.isoformat() if s.starts_at else None,
                "ends_at": s.ends_at.isoformat() if s.ends_at else None,
                "active": s.status == "active" and bool(s.ends_at and s.ends_at > now),
            }
            for s in sanctions
        ],
        "point_events": [
            {"kind": p.kind, "points": p.points, "at": p.created_at.isoformat(), "reason": p.reason}
            for p in session.execute(
                select(PointEvent)
                .where(PointEvent.resident_id == r.id)
                .order_by(PointEvent.id.desc())
                .limit(30)
            ).scalars()
        ],
        "tier_history": [
            {"at": t.at.isoformat(), "from": t.from_tier, "to": t.to_tier, "points": t.points}
            for t in session.execute(
                select(TierHistory)
                .where(TierHistory.resident_id == r.id)
                .order_by(TierHistory.id.desc())
                .limit(20)
            ).scalars()
        ],
    }


def confirmation_queue(session: Session, viewer_id: int, viewer_role: str) -> list[dict]:
    cfg = load_engine_config(session)
    rows = session.execute(
        select(Sanction, Resident.code)
        .join(Resident, Resident.id == Sanction.resident_id)
        .where(Sanction.status == "pending")
        .order_by(Sanction.issued_at)
    ).all()
    names = _names(
        session,
        {s.issued_by for s, _ in rows} | {s.evidence_reporter_id for s, _ in rows},
    )
    out = []
    for s, code in rows:
        rule = cfg.infractions[s.infraction_code]
        out.append(
            {
                "id": s.id,
                "resident_id": s.resident_id,
                "resident_code": code,
                "infraction_code": s.infraction_code,
                "label": rule.label,
                "severity": rule.severity,
                "duration_hours": rule.duration_hours,
                "issued_at": s.issued_at.isoformat(),
                "issued_by": _ref(names, s.issued_by),
                "evidence": {
                    "type": s.evidence_type,
                    "reporter": _ref(names, s.evidence_reporter_id),
                    "ref": s.evidence_ref,
                },
                "why_pending": "supervisor confirmation required"
                if needs_supervisor(rule)
                else "officer weekly cap reached",
                "can_confirm": viewer_role == "supervisor" and s.issued_by != viewer_id,
            }
        )
    return out


def appeals_queue(
    session: Session, viewer_id: int, viewer_role: str, now: datetime, include_closed: bool = False
) -> list[dict]:
    q = (
        select(Appeal, Sanction, Resident.code)
        .join(Sanction, Sanction.id == Appeal.sanction_id)
        .join(Resident, Resident.id == Sanction.resident_id)
        .order_by(Appeal.due_at)
    )
    if not include_closed:
        q = q.where(Appeal.status == "open")
    rows = session.execute(q).all()
    names = _names(session, {s.issued_by for _, s, _ in rows} | {a.reviewer_id for a, _, _ in rows})
    return [
        {
            "appeal_id": a.id,
            "sanction_id": s.id,
            "resident_code": code,
            "infraction_code": s.infraction_code,
            "status": a.status,
            "filed_at": a.filed_at.isoformat(),
            "due_at": a.due_at.isoformat() if a.due_at else None,
            "overdue": a.status == "open" and bool(a.due_at and a.due_at < now),
            "issued_by": _ref(names, s.issued_by),
            "reviewer": _ref(names, a.reviewer_id),
            "outcome_note": a.outcome_note,
            "can_review": a.status == "open"
            and viewer_role == "supervisor"
            and s.issued_by != viewer_id,
        }
        for a, s, code in rows
    ]


def outliers(session: Session, now: datetime) -> dict:
    settings = {**DEFAULT_OUTLIER, **get_current(session, "sanctions").payload.get("outlier", {})}
    since = now - timedelta(days=settings["window_days"])
    result: dict[str, Any] = {"settings": settings, "since": since.isoformat(), "groups": {}}
    for role in ("officer", "supervisor"):
        members = (
            session.execute(select(Staff).where(Staff.role == role, Staff.active.is_(True)))
            .scalars()
            .all()
        )
        stats: dict[str, StaffStats] = {}
        for m in members:
            rows = (
                session.execute(
                    select(Sanction.status).where(
                        Sanction.issued_by == m.id, Sanction.issued_at >= since
                    )
                )
                .scalars()
                .all()
            )
            applied = [x for x in rows if x in ("active", "overturned")]
            stats[m.username] = StaffStats(
                reports=len(rows),
                sanctions=len(applied),
                overturned=rows.count("overturned"),
                rejected=rows.count("rejected"),
            )
        flags = find_outliers(
            stats,
            z_threshold=settings["z_threshold"],
            min_peers=settings["min_peers"],
            min_count=settings["min_count"],
        )
        result["groups"][role] = [
            {
                "username": u,
                "reports": s.reports,
                "sanctions": s.sanctions,
                "overturned": s.overturned,
                "rejected": s.rejected,
                "flags": [
                    {
                        "metric": f.metric,
                        "value": round(f.value, 2),
                        "peer_mean": round(f.peer_mean, 2),
                        "z": f.z,
                    }
                    for f in flags[u]
                ],
            }
            for u, s in sorted(stats.items())
        ]
    result["flagged"] = sum(1 for g in result["groups"].values() for row in g if row["flags"])
    return result


def events(session: Session, limit: int = 40) -> list[dict]:
    rows = (
        session.execute(
            select(AuditLog)
            .where(AuditLog.action.in_(EVENT_ACTIONS))
            .order_by(AuditLog.seq.desc())
            .limit(min(limit, 200))
        )
        .scalars()
        .all()
    )
    names = _names(session, {r.actor_id for r in rows})
    res_ids = {
        int(r.target_id) for r in rows if r.target_type == "resident" and r.target_id.isdigit()
    }
    codes = {
        i: c
        for i, c in session.execute(
            select(Resident.id, Resident.code).where(Resident.id.in_(res_ids))
        ).all()
    }

    def target(r: AuditLog) -> str:  # show resident codes, not internal numbers
        if r.target_type == "resident" and r.target_id.isdigit():
            return codes.get(int(r.target_id), r.target_id)
        return r.target_id

    return [
        {
            "seq": r.seq,
            "ts": r.ts.isoformat(),
            "actor": names.get(r.actor_id, r.actor_role) if r.actor_id else r.actor_role,
            "action": r.action,
            "target": target(r),
            "reason_code": r.reason_code,
        }
        for r in rows
    ]


def summary(session: Session, viewer_id: int, viewer_role: str, now: datetime) -> dict:
    ro = roster(session, now)
    appeals = appeals_queue(session, viewer_id, viewer_role, now)
    show_outliers = viewer_role in ("supervisor", "admin", "auditor")
    return {
        "residents": len(ro),
        "pending_confirmations": session.execute(
            select(func.count()).where(Sanction.status == "pending")
        ).scalar(),
        "open_appeals": len(appeals),
        "overdue_appeals": sum(a["overdue"] for a in appeals),
        "offline_devices": sum(r["offline"] for r in ro),
        "outlier_flags": outliers(session, now)["flagged"] if show_outliers else None,
        "welfare_flags": len(welfare.all_flags(session, now)),
    }
