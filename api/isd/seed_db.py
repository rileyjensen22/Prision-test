"""Load seed data into Postgres (idempotent: skips if config already seeded)."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from isd import settings
from isd.auth import hash_device_token, hash_password
from isd.models import (
    ApprovedContentSource,
    ConfigVersion,
    Contact,
    Device,
    DeviceAssignment,
    JobListing,
    JobPartner,
    Resident,
    ReentryResource,
    Staff,
)
from isd.services import commissary, facility_model, points
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


_REENTRY_SEED = [
    {
        "title": "Georgia Department of Labor – Reentry Services",
        "description": "Sample — replace with real local resource. Job placement, resume help, and career counseling for people returning from incarceration.",
        "phone": "404-555-0100",
        "address": "148 Andrew Young International Blvd NE, Atlanta, GA 30303",
        "category": "employment",
    },
    {
        "title": "Georgia Legal Services – Prisoner Reentry Project",
        "description": "Sample — replace with real local resource. Free civil legal aid for returning citizens on housing, expungement, and benefits.",
        "phone": "404-555-0101",
        "address": "104 Marietta St NW, Atlanta, GA 30303",
        "category": "legal",
    },
    {
        "title": "Salvation Army – Adult Rehabilitation Center",
        "description": "Sample — replace with real local resource. Transitional housing and substance-use recovery support.",
        "phone": "404-555-0102",
        "address": "1000 Salvation Place, Atlanta, GA",
        "category": "housing",
    },
    {
        "title": "Georgia Gateway – Benefits Enrollment",
        "description": "Sample — replace with real local resource. Apply for SNAP, Medicaid, and other state benefits.",
        "phone": "877-555-0103",
        "address": "Online at gateway.ga.gov",
        "category": "benefits",
    },
    {
        "title": "Behavioral Health – Crisis Line",
        "description": "Sample — replace with real local resource. 24/7 crisis support; can connect to local mental-health services.",
        "phone": "800-555-0104",
        "address": "",
        "category": "mental_health",
    },
    {
        "title": "GA Dept. of Driver Services – ID Restoration",
        "description": "Sample — replace with real local resource. Help obtaining a state ID or driver's license after release.",
        "phone": "678-555-0105",
        "address": "2206 Eastview Pkwy, Conyers, GA 30013",
        "category": "id_documents",
    },
    {
        "title": "Reentry Council – Housing Assistance List",
        "description": "Sample — replace with real local resource. Curated list of landlords and shelters accepting returning citizens.",
        "phone": "404-555-0106",
        "address": "Contact facility case manager for current list",
        "category": "housing",
    },
]


def ensure_reference_data(session: Session) -> None:
    """The content allow-list and sample job listings (safe to run repeatedly)."""
    now = datetime.now(UTC)
    have = set(session.execute(select(ApprovedContentSource.name)).scalars())
    for name, protected in (
        ("Bundled public-domain texts", False),
        ("Bundled baseline texts", True),
    ):
        if name not in have:
            session.add(
                ApprovedContentSource(
                    name=name, kind="bundled", active=True, protected=protected, approved_at=now
                )
            )
    partner = session.execute(select(JobPartner).where(JobPartner.code == "MOCK_PARTNER")).scalar()
    if partner is None:
        partner = JobPartner(code="MOCK_PARTNER", name="Sample Work Partner (demo)", active=True)
        session.add(partner)
        session.flush()
    existing = {j.code: j for j in session.execute(select(JobListing)).scalars()}
    have_jobs = set(existing)
    for code, title, kind, pay, text in (
        (
            "TRANSCRIBE",
            "Transcribe public-domain books",
            "transcription_public_domain",
            25,
            "Correct lines from public-domain books that were scanned badly. No personal data.",
        ),
        (
            "CAPTION",
            "Caption educational clips",
            "captioning",
            20,
            "Write a short caption for a described scene from a course clip. No personal data.",
        ),
        (
            "SENTENCES",
            "Label sentences",
            "labeling_non_personal",
            10,
            "Say if a public-domain or made-up sentence is a statement, question or exclamation.",
        ),
    ):
        if code in existing and existing[code].partner_id is None:  # older databases
            existing[code].partner_id, existing[code].pay_per_task_cents = partner.id, pay
        if code not in have_jobs:
            session.add(
                JobListing(
                    code=code,
                    title=title,
                    task_type=kind,
                    description=text,
                    active=True,
                    created_at=now,
                    partner_id=partner.id,
                    pay_per_task_cents=pay,
                )
            )
    # Reentry resources — seed once if table is empty
    if not session.execute(select(ReentryResource.id).limit(1)).first():
        for row in _REENTRY_SEED:
            session.add(ReentryResource(**row))
    session.flush()


def seed_database(session: Session, data: dict) -> bool:
    if settings.ENV == "production":
        raise RuntimeError(
            "refusing to load the synthetic seed (predictable tokens and passwords) in production"
        )
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
    # The facility at the default (demo) scale; the first cells take the seed residents' names.
    cells = facility_model.build(
        session,
        facility_model.scale_named(session, data.get("scale")),
        cell_codes=[r["cell"] for r in data["residents"]],
    )
    for r, cell in zip(data["residents"], cells, strict=False):
        res = Resident(
            code=r["id"],
            display_name=r["display_name"],
            language=r["language"],
            prior_returns=r["prior_returns"],
            prior_returns_source="synthetic seed",
        )
        session.add(res)
        codes[r["id"]] = res
        device = Device(
            code=f"DEV-{r['cell']}", token_hash=hash_device_token(dev_device_token(r["cell"]))
        )
        session.add(device)
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
