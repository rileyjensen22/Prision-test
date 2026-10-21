"""Public log export (CLAUDE.md section 10). Off by default; an operator turns it on in compliance
config (an audit-logged change). Writes static files only: nothing here is served live."""

import csv
import hashlib
import html
import json
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from isd.engine.config import EngineConfig
from isd.engine.public_log import RECORD_FIELDS, aggregate, assert_clean, build_record
from isd.models import Appeal, Resident, Sanction, Staff
from isd.services.audit import SYSTEM, append_audit
from isd.services.config_store import get_current
from isd.services.entitlement_service import load_engine_config


class PublicLogDisabled(RuntimeError):
    """The operator has not enabled the public log (public_log_enabled is false)."""


def _appeal_state(session: Session, sanction_id: int) -> str:
    a = (
        session.execute(
            select(Appeal).where(Appeal.sanction_id == sanction_id).order_by(Appeal.id.desc())
        )
        .scalars()
        .first()
    )
    return "none" if a is None else a.status


def collect_records(
    session: Session, now: datetime, salt: str, cfg: EngineConfig | None = None
) -> list[dict]:
    cfg = cfg or load_engine_config(session)
    roles = {i: r for i, r in session.execute(select(Staff.id, Staff.role)).all()}
    rows = session.execute(
        select(Sanction, Resident.code)
        .join(Resident, Resident.id == Sanction.resident_id)
        .order_by(Sanction.id)
    ).all()
    out = []
    for s, code in rows:
        rule = cfg.infractions.get(s.infraction_code)
        if s.status == "active" and s.starts_at and s.ends_at:
            served = (min(now, s.ends_at) - s.starts_at).total_seconds() / 3600
        elif s.status == "overturned" and s.starts_at and s.overturned_at:
            served = (s.overturned_at - s.starts_at).total_seconds() / 3600
        else:
            served = 0.0
        out.append(
            build_record(
                sanction_id=s.id,
                resident_code=code,
                issued_at=s.issued_at,
                code=s.infraction_code,
                severity=rule.severity if rule else "unknown",
                duration_hours=rule.duration_hours if rule else 0,
                hours_served=served,
                issued_by_role=roles.get(s.issued_by, "system") if s.issued_by else "system",
                confirmed_by_role=roles.get(s.confirmed_by) if s.confirmed_by else None,
                status=s.status,
                ends_at=s.ends_at,
                appeal=_appeal_state(session, s.id),
                now=now,
                salt=salt,
            )
        )
    return out


def _html(summary: dict, records: list[dict], day: str) -> str:
    esc = html.escape

    def table(head: list[str], rows: list[list]) -> str:
        th = "".join(f"<th>{esc(h)}</th>" for h in head)
        body = "".join(
            "<tr>" + "".join(f"<td>{esc(str(c))}</td>" for c in r) + "</tr>" for r in rows
        )
        return f"<table><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table>"

    roles = [[r, *v.values()] for r, v in summary["by_issuing_role"].items()]
    role_head = ["Role", "Issued", "Applied", "Rejected", "Overturned on appeal", "Appealed"]
    csp = "default-src 'none'; style-src 'unsafe-inline'"
    css = (
        "body{font:16px/1.5 system-ui;max-width:60rem;margin:2rem auto;padding:0 1rem}"
        "table{border-collapse:collapse;width:100%;margin:1rem 0}"
        "td,th{border:1px solid #bbb;padding:.35rem .5rem;text-align:left}"
    )
    intro = (
        f"Generated {esc(day)}. Residents are shown only by random-looking codes and dates only by "
        "week. No names, staff identities, case details or free text are published. "
        "Counts under the threshold show as &lt;k."
    )
    recent = [[r[f] if r[f] is not None else "" for f in RECORD_FIELDS] for r in records[-500:]]
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        f'<meta http-equiv="Content-Security-Policy" content="{csp}">'
        f"<title>Sanctions transparency report</title><style>{css}</style></head><body>"
        f"<h1>Sanctions transparency report</h1><p>{intro}</p>"
        f"<h2>By role that recorded the infraction</h2>{table(role_head, roles)}"
        f"<h2>By reason code</h2>{table(['Code', 'Count'], list(summary['by_code'].items()))}"
        f"<h2>Records ({len(records)})</h2>{table(list(RECORD_FIELDS), recent)}"
        "</body></html>"
    )


def export(session: Session, now: datetime, salt: str, out_dir: Path) -> dict:
    compliance = get_current(session, "compliance").payload
    if not compliance.get("public_log_enabled"):
        raise PublicLogDisabled("public_log_enabled is false; an operator must turn it on first")
    records = [assert_clean(r) for r in collect_records(session, now, salt)]
    minimum = int(compliance.get("public_log_min_cell", 3))
    summary = aggregate(records, minimum)
    day = now.date().isoformat()

    out_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "records.json": json.dumps(
            {"generated": day, "fields": list(RECORD_FIELDS), "records": records}, indent=2
        ),
        "summary.json": json.dumps({"generated": day, "min_cell": minimum, **summary}, indent=2),
        "index.html": _html(summary, records, day),
        "README.txt": (
            "Public sanctions log export.\n"
            "Included: pseudonymous resident and event codes, week issued, reason code, severity,\n"
            "scheduled and served hours, issuing and confirming ROLE, outcome, appeal result, and\n"
            "per-role totals.\n"
            "Excluded: names, internal ids, staff identities, cells and devices, evidence, notes,\n"
            "and any free text.\n"
        ),
    }
    csv_path = out_dir / "records.csv"
    with csv_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(RECORD_FIELDS))
        w.writeheader()
        w.writerows(records)
    for name, content in files.items():
        (out_dir / name).write_text(content)
    manifest = {
        n: hashlib.sha256((out_dir / n).read_bytes()).hexdigest() for n in (*files, "records.csv")
    }
    (out_dir / "manifest.json").write_text(
        json.dumps({"generated": day, "sha256": manifest}, indent=2)
    )
    append_audit(
        session,
        SYSTEM,
        "public_log_export",
        "public_log",
        day,
        "PUBLIC_LOG_EXPORT",
        payload={
            "records": len(records),
            "manifest_sha256": hashlib.sha256(
                json.dumps(manifest, sort_keys=True).encode()
            ).hexdigest(),
        },
    )
    return {
        "records": len(records),
        "dir": str(out_dir),
        "files": sorted([*files, "records.csv", "manifest.json"]),
    }
