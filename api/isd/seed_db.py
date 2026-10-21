"""Load seed data into Postgres (idempotent: skips if config already seeded)."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from isd.auth import hash_device_token, hash_password
from isd.models import (
    ApprovedContentSource,
    Cell,
    ConfigVersion,
    Contact,
    Device,
    DeviceAssignment,
    JobListing,
    Resident,
    Staff,
)
from isd.services import commissary, points
from isd.services.audit import SYSTEM, append_audit
from isd.services.config_store import get_current

DEV_PASSWORD = "dev-password-not-secret"  # synthetic dev accounts only


def dev_device_token(cell: str) -> str:
    """Predictable tokens for synthetic dev devices only. Real devices get random secrets."""
    return f"dev-device-token-{cell}"


def ensure_config(session: Session, config: dict) -> None:
    """Adds any config section that is missing (older databases gain new sections)."""
    for name, payload in config.items():
        if get_current(session, name) is None:
            session.add(ConfigVersion(name=name, version=1, payload=payload, reason="initial seed"))
            session.flush()
            append_audit(
                session,
                SYSTEM,
                "config_change",
                "config",
                name,
                "CONFIG_SEED",
                payload={"version": 1},
            )


def ensure_reference_data(session: Session) -> None:
    """The content allow-list and sample job listings (safe to run repeatedly)."""
    now = datetime.now(UTC)
    if session.execute(select(ApprovedContentSource.id)).first() is None:
        session.add(
            ApprovedContentSource(
                name="Bundled public-domain texts", kind="bundled", active=True, approved_at=now
            )
        )
    if session.execute(select(JobListing.id)).first() is None:
        session.add_all(
            [
                JobListing(
                    code="TRANSCRIBE",
                    title="Transcribe public-domain books",
                    task_type="transcription_public_domain",
                    active=True,
                    created_at=now,
                    description="Type up public-domain book pages. No personal data is involved.",
                ),
                JobListing(
                    code="CAPTION",
                    title="Caption educational videos",
                    task_type="captioning",
                    active=True,
                    created_at=now,
                    description="Write captions for course videos.",
                ),
            ]
        )
    session.flush()


def seed_database(session: Session, data: dict) -> bool:
    if get_current(session, "tiers"):
        ensure_config(session, data["config"])
        ensure_reference_data(session)
        return False
    pw_hash = hash_password(DEV_PASSWORD)
    for s in data["staff"]:
        session.add(Staff(username=s["username"], role=s["role"], password_hash=pw_hash))
    ensure_config(session, data["config"])
    ensure_reference_data(session)
    session.flush()
    now = datetime.now(UTC)
    codes: dict[str, Resident] = {}
    for r in data["residents"]:
        res = Resident(
            code=r["id"],
            display_name=r["display_name"],
            language=r["language"],
            prior_returns=r["prior_returns"],
            prior_returns_source="synthetic seed",
        )
        session.add(res)
        codes[r["id"]] = res
        cell = Cell(code=r["cell"])
        device = Device(
            code=f"DEV-{r['cell']}", token_hash=hash_device_token(dev_device_token(r["cell"]))
        )
        session.add_all([cell, device])
        session.flush()
        session.add(DeviceAssignment(device_id=device.id, cell_id=cell.id, resident_id=res.id))
        append_audit(
            session,
            SYSTEM,
            "device_assignment",
            "resident",
            r["id"],
            "SEED_ASSIGN",
            payload={"device": device.code, "cell": cell.code},
        )
    for i, c in enumerate(data["contacts"]):
        session.add(
            Contact(
                resident_id=codes[c["resident_id"]].id,
                name=c["name"],
                type=c["type"],
                phone_ref=f"555-01{i:02d}",
            )
        )
    session.flush()
    for r in data["residents"]:  # starting points and a small family deposit
        res = codes[r["id"]]
        if r["points"]:
            points.record_points(
                session, SYSTEM, res.id, "seed_adjustment", r["points"], "system", now
            )
            points.evaluate_tier(session, res.id, now)
        commissary.deposit(session, SYSTEM, res.id, 2500, "seed", f"seed-{r['id']}", now)
    return True
