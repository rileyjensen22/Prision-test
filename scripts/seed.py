"""Generate synthetic seed data (no real names/IDs); write var/seed.json and load Postgres."""

import json
import random
from pathlib import Path

from isd import settings
from isd.config_loader import load_config
from isd.seed_db import seed_database
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]

ROLES = [
    "officer",
    "officer",
    "officer",
    "supervisor",
    "supervisor",
    "admin",
    "auditor",
]


def build_seed(seed: int = 1) -> dict:
    rng = random.Random(seed)
    config = load_config()
    staff = [
        {
            "id": f"STAFF-{i + 1:03d}",
            "username": f"{role}{i + 1}",
            "role": role,
        }
        for i, role in enumerate(ROLES)
    ]
    residents = [
        {
            "id": f"RES-{i + 1:04d}",
            "display_name": f"Synthetic Resident {i + 1}",
            "cell": f"A-{i + 1:02d}",
            "language": rng.choice(["en", "es"]),
            "prior_returns": rng.choice([0, 0, 0, 1, 2, 4]),
            "points": rng.choice([0, 40, 60, 120, 300, 520]),
        }
        for i in range(12)
    ]
    contacts = [
        {
            "resident_id": r["id"],
            "name": f"Synthetic Contact {r['id'][-4:]}-{k}",
            "type": t,
        }
        for r in residents[:6]
        for k, t in enumerate(["family", "attorney"])
    ]
    return {
        "config": config,
        "staff": staff,
        "residents": residents,
        "contacts": contacts,
    }


def main() -> None:
    out = ROOT / "var" / "seed.json"
    out.parent.mkdir(exist_ok=True)
    data = build_seed()
    out.write_text(json.dumps(data, indent=2, sort_keys=True))
    print(
        f"Wrote {len(data['staff'])} staff, {len(data['residents'])} residents -> {out}"
    )
    try:
        with (
            Session(create_engine(settings.MIGRATION_DATABASE_URL)) as session,
            session.begin(),
        ):
            loaded = seed_database(session, data)
        print("Database seeded." if loaded else "Database already seeded; skipped.")
    except OperationalError as exc:  # DB unreachable: JSON output is still written
        print(
            f"Database not seeded ({type(exc).__name__}); is Postgres up? (make db-local)"
        )


if __name__ == "__main__":
    main()
