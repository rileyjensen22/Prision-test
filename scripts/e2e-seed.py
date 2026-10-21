"""Create the isd_e2e database with known synthetic residents for Playwright. Writes fixtures JSON."""

import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from alembic import command
from alembic.config import Config
from isd import settings
from isd.auth import hash_device_token, hash_password
from isd.config_loader import load_config
from isd.models import Cell, Contact, Device, DeviceAssignment, Resident, Staff
from isd.services import commissary, points, sanctions
from isd.services.audit import SYSTEM, Actor
from isd.services.config_store import set_config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
DB = os.environ.get("E2E_DB", "isd_e2e")
OUT = ROOT / "web" / "e2e" / ".fixtures.json"


def main() -> None:
    admin = create_engine(
        make_url(settings.MIGRATION_DATABASE_URL), isolation_level="AUTOCOMMIT"
    )
    with admin.connect() as c:
        c.execute(text(f"DROP DATABASE IF EXISTS {DB} WITH (FORCE)"))
        c.execute(text(f"CREATE DATABASE {DB}"))
    url = (
        make_url(settings.MIGRATION_DATABASE_URL)
        .set(database=DB)
        .render_as_string(False)
    )
    cfg = Config(str(ROOT / "api" / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "api" / "alembic"))
    cfg.attributes["url"] = url
    command.upgrade(cfg, "head")

    now = datetime.now(UTC)
    tokens: dict[str, str] = {}
    with Session(create_engine(url)) as s, s.begin():
        for name, payload in load_config().items():
            set_config(s, SYSTEM, name, payload, "e2e seed")
        pw = hash_password("pw")

        def new_officer(
            key: str,
        ) -> Actor:  # one per sanction so the weekly cap never interferes
            st = Staff(username=f"e2e_officer_{key}", role="officer", password_hash=pw)
            s.add(st)
            s.flush()
            return Actor(st.id, "officer")

        def resident(
            key,
            lang="en",
            prior=0,
            certs=0,
            sanction=None,
            issued_ago=timedelta(hours=1),
            start_points=0,
            contacts=(),
            funds=0,
        ):
            r = Resident(
                code=f"E2E-{key.upper()}",
                display_name=f"Synthetic {key}",
                language=lang,
                prior_returns=prior,
            )
            cell, dev = Cell(code=f"E2E-{key}"), Device(code=f"E2E-DEV-{key}")
            tokens[key] = f"e2e-token-{key}"
            dev.token_hash = hash_device_token(tokens[key])
            s.add_all([r, cell, dev])
            s.flush()
            s.add(DeviceAssignment(device_id=dev.id, cell_id=cell.id, resident_id=r.id))
            if start_points:
                points.record_points(
                    s,
                    SYSTEM,
                    r.id,
                    "seed_adjustment",
                    start_points,
                    "system",
                    now - timedelta(days=2),
                )
                points.evaluate_tier(s, r.id, now - timedelta(days=2))
            for n, kind in enumerate(contacts):
                s.add(
                    Contact(
                        resident_id=r.id,
                        name=f"Synthetic {kind} {key}",
                        type=kind,
                        phone_ref=f"555-02{n:02d}",
                    )
                )
            if funds:
                commissary.deposit(s, SYSTEM, r.id, funds, "e2e", f"e2e-{key}", now)
            for _ in range(certs):
                points.add_point_event(
                    s, SYSTEM, r.id, "program_certificate", now - timedelta(days=1)
                )
            if sanction:
                sanctions.issue_sanction(
                    s, new_officer(key), r.id, sanction, now - issued_ago
                )

        resident(
            "alice", certs=2, sanction="DISRUPT"
        )  # tier 3, calls/texts/video locked ~23h
        resident(
            "benito", lang="es", sanction="CELL_MESS"
        )  # Spanish, commissary locked
        resident("carla", prior=10, certs=3)  # earned tier 4, ceiling 2
        resident("dan", sanction="CELL_MESS")  # appeal flow
        resident(
            "eve", sanction="DISRUPT", issued_ago=timedelta(hours=23, minutes=40)
        )  # ends in 20 min
        resident("fay")  # clean; request-staff flows
        # Demo loop: 60 points, one basic course (+50) crosses 100 and lifts calls 15 -> 20 minutes
        resident("gina", start_points=60, contacts=("family", "attorney"))
        resident("hal", funds=5000)  # commissary shopper, tier 1
        resident("ivy", contacts=("family", "attorney"))  # call flows
    OUT.write_text(
        json.dumps({"tokens": tokens, "generated_at": now.isoformat()}, indent=2)
    )
    print(f"e2e database {DB} ready; fixtures -> {OUT}")


if __name__ == "__main__":
    sys.exit(main())
