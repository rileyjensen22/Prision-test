"""Generate synthetic seed data (no real names/IDs). Phase 0: writes var/seed.json.

Phase 1 will load the same data into Postgres via the data model.
"""

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

from argon2 import PasswordHasher
from isd.config_loader import load_config

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
    ph = PasswordHasher()
    dev_hash = ph.hash("dev-password-not-secret")
    staff = [
        {
            "id": f"STAFF-{i + 1:03d}",
            "username": f"{role}{i + 1}",
            "role": role,
            "password_hash": dev_hash,
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
            "points": rng.choice([0, 40, 120, 300, 520]),
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
        f"Seeded {len(data['staff'])} staff, {len(data['residents'])} residents -> {out}"
    )


if __name__ == "__main__":
    main()
