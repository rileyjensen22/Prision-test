"""Build the full-size facility with synthetic residents: `make seed-full`.

5 hubs x 6 lines x 4 floors x 16 cells = 1,920 cells (scale `full` in config/facility.yaml), with a
resident and a device in 90% of them. Needs an empty database (run `make migrate` on a fresh one),
refuses to run in production, and uses predictable development tokens for the devices.
"""

import argparse
import sys
from datetime import UTC, datetime

from isd import settings
from isd.auth import hash_password
from isd.config_loader import load_config
from isd.models import Staff
from isd.seed_db import (
    DEV_PASSWORD,
    dev_device_token,
    ensure_config,
    ensure_reference_data,
)
from isd.services import facility_model
from isd.services.config_store import get_current
from isd.synthetic import populate
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

STAFF = [("officer1", "officer"), ("officer2", "officer"), ("supervisor1", "supervisor"),
         ("supervisor2", "supervisor"), ("admin1", "admin"), ("auditor1", "auditor")]  # fmt: skip


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", default="full")
    ap.add_argument("--occupancy", type=float, default=0.9)
    args = ap.parse_args()
    if settings.ENV == "production":
        print("refusing to load synthetic data in production", file=sys.stderr)
        return 1
    try:
        with (
            Session(create_engine(settings.MIGRATION_DATABASE_URL)) as session,
            session.begin(),
        ):
            if get_current(session, "tiers"):
                print(
                    "The database already has data; use an empty one (make db-local, make migrate)."
                )
                return 1
            now = datetime.now(UTC)
            ensure_config(session, load_config())
            ensure_reference_data(session)
            pw = hash_password(DEV_PASSWORD)
            session.add_all(
                Staff(username=u, role=r, password_hash=pw) for u, r in STAFF
            )
            tokens = populate(
                session,
                facility_model.scale_named(session, args.scale),
                occupancy=args.occupancy,
                now=now,
                token_for=lambda cell: dev_device_token(cell),
            )
            from isd.models import Cell

            cells = session.execute(select(func.count()).select_from(Cell)).scalar()
        print(
            f"Built {cells} cells and {len(tokens)} occupied cells with a device each."
        )
    except OperationalError as exc:
        print(
            f"Database not reachable ({type(exc).__name__}); is Postgres up? (make db-local)"
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
