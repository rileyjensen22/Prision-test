"""Read models for the staff dashboard. Everything here is read-only."""

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from isd.engine.authority import needs_supervisor
from isd.engine.outliers import StaffStats, find_outliers
from isd.models import (
    Appeal,
    AttorneyCallRequest,
    AuditLog,
    Cell,
    CommissaryOrder,
    DepositImport,
    Device,
    DeviceAssignment,
    Floor,
    Grievance,
    HealthRequest,
    Hub,
    Line,
    PointEvent,
    Resident,
    Sanction,
    Staff,
    TierHistory,
)
from isd.services import facility_model as facility
from isd.services import out_of_cell, welfare
from isd.services.config_store import get_current
from isd.services.entitlement_service import (
    get_entitlements,
    get_entitlements_many,
    load_engine_config,
)
from isd.services.points import total_points, total_points_many

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


def _placement_query(hub: str | None, line: str | None, floor: int | None, q: str | None):
    """Resident ids on the unit now (released residents excluded), narrowed by where they live or
    by a search on code or cell, in code order."""
    stmt = (
        select(Resident.id)
        .select_from(Resident)
        .outerjoin(
            DeviceAssignment,
            (DeviceAssignment.resident_id == Resident.id) & DeviceAssignment.ended_at.is_(None),
        )
        .outerjoin(Cell, Cell.id == DeviceAssignment.cell_id)
        .where(Resident.released_at.is_(None))
    )
    if hub or line or floor:
        stmt = stmt.join(Floor, Floor.id == Cell.floor_id).join(Line, Line.id == Floor.line_id)
        if hub:
            stmt = stmt.join(Hub, Hub.id == Line.hub_id).where(Hub.code == hub)
        if line:
            stmt = stmt.where(Line.code == line)
        if floor:
            stmt = stmt.where(Floor.level == floor)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(Resident.code.ilike(like) | Cell.code.ilike(like))
    return stmt.order_by(Resident.code)


def roster_page(
    session: Session,
    now: datetime,
    *,
    hub: str | None = None,
    line: str | None = None,
    floor: int | None = None,
    q: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    """One page of the roster for a hub, line or floor. Entitlements are worked out only for the
    residents on the page, so a facility of any size costs the same per page."""
    ids_stmt = _placement_query(hub, line, floor, q)
    total = session.execute(
        select(func.count()).select_from(ids_stmt.order_by(None).subquery())
    ).scalar()
    ids = list(session.execute(ids_stmt.limit(limit).offset(offset)).scalars())
    return {"total": total, "rows": roster(session, now, ids=ids)}


def lookup(
    session: Session,
    *,
    q: str | None = None,
    unit: str | None = None,
    line: str | None = None,
    floor: int | None = None,
    limit: int = 50,
) -> list[dict]:
    """A light list of residents to pick from: no entitlements, no sanctions."""
    stmt = (
        select(
            Resident.id,
            Resident.code,
            Resident.display_name,
            Cell.code,
            Cell.unit,
            Floor.level,
            Device.code,
        )
        .select_from(Resident)
        .outerjoin(
            DeviceAssignment,
            (DeviceAssignment.resident_id == Resident.id) & DeviceAssignment.ended_at.is_(None),
        )
        .outerjoin(Cell, Cell.id == DeviceAssignment.cell_id)
        .outerjoin(Device, Device.id == DeviceAssignment.device_id)
        .outerjoin(Floor, Floor.id == Cell.floor_id)
        .where(Resident.released_at.is_(None))
    )
    if unit:
        stmt = stmt.where(Cell.unit == unit)
    if line:
        stmt = stmt.join(Line, Line.id == Floor.line_id).where(Line.code == line)
    if floor:
        stmt = stmt.where(Floor.level == floor)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(Resident.code.ilike(like) | Cell.code.ilike(like))
    rows = session.execute(stmt.order_by(Resident.code).limit(limit)).all()
    return [
        {
            "resident_id": rid,
            "code": code,
            "display_name": name,
            "cell": cell,
            "unit": unit_,
            "floor": level,
            "device": device,
        }
        for rid, code, name, cell, unit_, level, device in rows
    ]


def roster(session: Session, now: datetime, ids: list[int] | None = None) -> list[dict]:
    """One row per resident (or per id given). A fixed number of queries however many residents
    there are."""
    cfg = load_engine_config(session)
    offline_after = timedelta(
        minutes=int(get_current(session, "compliance").payload["offline_alert_minutes"])
    )
    q = select(Resident).where(Resident.released_at.is_(None)).order_by(Resident.code)
    if ids is not None:
        q = q.where(Resident.id.in_(ids))
    residents = session.execute(q).scalars().all()
    ids = [r.id for r in residents]
    placed = {
        rid: (device, cell, level, line_code, hub_code)
        for rid, device, cell, level, line_code, hub_code in session.execute(
            select(DeviceAssignment.resident_id, Device, Cell, Floor.level, Line.code, Hub.code)
            .join(Device, Device.id == DeviceAssignment.device_id)
            .join(Cell, Cell.id == DeviceAssignment.cell_id)
            .outerjoin(Floor, Floor.id == Cell.floor_id)
            .outerjoin(Line, Line.id == Floor.line_id)
            .outerjoin(Hub, Hub.id == Line.hub_id)
            .where(DeviceAssignment.ended_at.is_(None), DeviceAssignment.resident_id.in_(ids))
        )
    }
    ents = get_entitlements_many(session, ids, now, cfg)
    active: dict[int, list[Sanction]] = {}
    for s in session.execute(
        select(Sanction).where(
            Sanction.status == "active", Sanction.ends_at > now, Sanction.resident_id.in_(ids)
        )
    ).scalars():
        active.setdefault(s.resident_id, []).append(s)
    pending = dict(
        session.execute(
            select(Sanction.resident_id, func.count())
            .where(Sanction.status == "pending", Sanction.resident_id.in_(ids))
            .group_by(Sanction.resident_id)
        ).all()
    )
    open_appeals = dict(
        session.execute(
            select(Sanction.resident_id, func.count())
            .select_from(Appeal)
            .join(Sanction, Sanction.id == Appeal.sanction_id)
            .where(Appeal.status == "open", Sanction.resident_id.in_(ids))
            .group_by(Sanction.resident_id)
        ).all()
    )
    points = total_points_many(session, ids, now)
    out = []
    for r in residents:
        device, cell, level, line_code, hub_code = placed.get(r.id, (None,) * 5)
        ent = ents[r.id]
        last_sync = device.last_sync_at if device else None
        out.append(
            {
                "resident_id": r.id,
                "code": r.code,
                "display_name": r.display_name,
                "cell": cell.code if cell else None,
                "unit": cell.unit if cell else None,
                "hub": hub_code,
                "line": line_code,
                "floor": level,
                "device": device.code if device else None,
                "last_sync_at": last_sync.isoformat() if last_sync else None,
                "offline": device is not None
                and (last_sync is None or now - last_sync > offline_after),
                "tier": {
                    "earned": ent.earned_tier,
                    "ceiling": ent.ceiling_tier,
                    "effective": ent.effective_tier,
                },
                "points": points.get(r.id, 0),
                "active_sanctions": [
                    {"id": s.id, "code": s.reason_code, "ends_at": s.ends_at.isoformat()}
                    for s in active.get(r.id, [])
                ],
                "pending_sanctions": pending.get(r.id, 0),
                "open_appeals": open_appeals.get(r.id, 0),
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
        "released_at": r.released_at.isoformat() if r.released_at else None,
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


def facility_overview(session: Session, now: datetime) -> dict:
    after = timedelta(
        minutes=int(get_current(session, "compliance").payload["offline_alert_minutes"])
    )
    return facility.overview(session, now, after)


def _safe_count(session: Session, query) -> int:
    """Run a count query; return 0 if the table doesn't exist yet (migration not applied)."""
    try:
        result = session.execute(query).scalar()
        return result or 0
    except Exception:
        session.rollback()
        return 0


def _offline_devices(session: Session, now: datetime) -> int:
    after = timedelta(
        minutes=int(get_current(session, "compliance").payload["offline_alert_minutes"])
    )
    return session.execute(
        select(func.count(DeviceAssignment.id))
        .join(Device, Device.id == DeviceAssignment.device_id)
        .join(Resident, Resident.id == DeviceAssignment.resident_id)
        .where(
            DeviceAssignment.ended_at.is_(None),
            Resident.released_at.is_(None),
            (Device.last_sync_at.is_(None)) | (Device.last_sync_at < now - after),
        )
    ).scalar()


def summary(session: Session, viewer_id: int, viewer_role: str, now: datetime) -> dict:
    """The dashboard numbers. Counts come from aggregate queries: nothing is worked out per
    resident, so this costs about the same for 20 residents as for 2,000."""
    appeals = appeals_queue(session, viewer_id, viewer_role, now)
    show_outliers = viewer_role in ("supervisor", "admin", "auditor")
    flags = welfare.all_flags(session, now, max_age_seconds=300)  # polled: not every refresh
    return {
        "residents": session.execute(
            select(func.count()).select_from(Resident).where(Resident.released_at.is_(None))
        ).scalar(),
        "pending_confirmations": session.execute(
            select(func.count()).where(Sanction.status == "pending")
        ).scalar(),
        "open_appeals": len(appeals),
        "overdue_appeals": sum(a["overdue"] for a in appeals),
        "offline_devices": _offline_devices(session, now),
        "outlier_flags": outliers(session, now)["flagged"] if show_outliers else None,
        "welfare_flags": len(flags),
        "welfare_escalated": sum(f["escalated"] for r in flags for f in r["flags"]),
        "below_minimum": len(out_of_cell.below_minimum(session, now)),
        # None until a reconciliation has run (or for roles that do not see finance)
        "ledger_ok": _ledger_ok(session) if show_outliers else None,
        # New queue counts — wrapped in try/except in case migration hasn't run yet
        "open_health_requests": _safe_count(
            session, select(func.count()).select_from(HealthRequest).where(HealthRequest.status == "open")
        ),
        "open_grievances": _safe_count(
            session, select(func.count()).select_from(Grievance).where(Grievance.status == "open")
        ),
        "pending_attorney_calls": _safe_count(
            session, select(func.count()).select_from(AttorneyCallRequest).where(AttorneyCallRequest.status == "pending")
        ),
        "commissary_orders_waiting": _safe_count(
            session, select(func.count()).select_from(CommissaryOrder).where(CommissaryOrder.status == "new")
        ),
        "deposit_imports_pending": _safe_count(
            session, select(func.count()).select_from(DepositImport).where(DepositImport.status == "pending")
        ),
    }


def _ledger_ok(session: Session) -> bool | None:
    from isd.models import ReconciliationRun

    last = session.execute(
        select(ReconciliationRun.ok).order_by(ReconciliationRun.id.desc()).limit(1)
    ).scalar()
    return last
