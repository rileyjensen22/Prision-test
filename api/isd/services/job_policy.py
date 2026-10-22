"""Whether a sanction pauses work. OFF by default (`jobs.suspend_on_sanction`).

This is the only place work and sanctions meet. With the flag off it never reads a sanction, so
work access is fully independent of tier and sanctions (invariant 7). With it on, only sanctions
whose scope is listed in `suspend_scopes` pause *new tasks*; the resident stays enrolled and pay
already earned is always paid out. The pause is a lock, so it carries a reason code, an end time
and how to appeal (invariant 5).
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from isd.models import Sanction
from isd.services.config_store import get_current


def suspension(session: Session, resident_id: int, now: datetime) -> dict | None:
    cfg = get_current(session, "jobs").payload
    if not cfg["suspend_on_sanction"]:
        return None
    s = session.execute(
        select(Sanction)
        .where(
            Sanction.resident_id == resident_id,
            Sanction.status == "active",
            Sanction.scope.in_(cfg["suspend_scopes"]),
            Sanction.starts_at <= now,
            Sanction.ends_at > now,
        )
        .order_by(Sanction.ends_at.desc())
        .limit(1)
    ).scalar()
    if s is None:
        return None
    return {
        "code": s.reason_code,
        "ends_at": s.ends_at.isoformat(),
        "how_to_appeal": "appeal",
        "sanction_id": s.id,
    }
