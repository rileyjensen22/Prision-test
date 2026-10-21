"""Load seed data into Postgres (idempotent: skips if config already seeded)."""

from sqlalchemy.orm import Session

from isd.auth import hash_password
from isd.models import Cell, ConfigVersion, Contact, Device, DeviceAssignment, Resident, Staff
from isd.services.audit import SYSTEM, append_audit
from isd.services.config_store import get_current

DEV_PASSWORD = "dev-password-not-secret"  # synthetic dev accounts only


def seed_database(session: Session, data: dict) -> bool:
    if get_current(session, "tiers"):
        return False
    pw_hash = hash_password(DEV_PASSWORD)
    for s in data["staff"]:
        session.add(Staff(username=s["username"], role=s["role"], password_hash=pw_hash))
    for name, payload in data["config"].items():
        session.add(ConfigVersion(name=name, version=1, payload=payload, reason="initial seed"))
        append_audit(
            session, SYSTEM, "config_change", "config", name, "CONFIG_SEED", payload={"version": 1}
        )
    session.flush()
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
        device = Device(code=f"DEV-{r['cell']}")
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
    for c in data["contacts"]:
        session.add(Contact(resident_id=codes[c["resident_id"]].id, name=c["name"], type=c["type"]))
    return True
