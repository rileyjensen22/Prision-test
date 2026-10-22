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
from isd.engine.authority import Evidence
from isd.models import (
    CallRecord,
    Cell,
    Contact,
    Device,
    DeviceAssignment,
    Resident,
    Staff,
)
from isd.seed_db import ensure_reference_data
from isd.services import commissary, points, sanctions
from isd.services.audit import SYSTEM, Actor
from isd.services.config_store import set_config
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
STAFF_PASSWORD = "e2e-pass"
STAFF = {  # key used by the Playwright helpers -> account
    "e2e_officer": "officer",
    "e2e_colleague": "officer",
    "e2e_heavy": "officer",
    "e2e_sup1": "supervisor",
    "e2e_sup2": "supervisor",
    "e2e_admin": "admin",
    "e2e_auditor": "auditor",
}
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
        ensure_reference_data(s)
        pw = hash_password("pw")
        staff_pw = hash_password(STAFF_PASSWORD)
        for username, role in STAFF.items():
            s.add(Staff(username=username, role=role, password_hash=staff_pw))
        s.flush()

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
            assigned_days_ago=0,
            quiet_after_days=None,
            unit="A",
        ):
            r = Resident(
                code=f"E2E-{key.upper()}",
                display_name=f"Synthetic {key}",
                language=lang,
                prior_returns=prior,
            )
            cell, dev = (
                Cell(code=f"E2E-{key}", unit=unit),
                Device(code=f"E2E-DEV-{key}"),
            )
            tokens[key] = f"e2e-token-{key}"
            dev.token_hash = hash_device_token(tokens[key])
            s.add_all([r, cell, dev])
            s.flush()
            s.add(
                DeviceAssignment(
                    device_id=dev.id,
                    cell_id=cell.id,
                    resident_id=r.id,
                    assigned_at=now - timedelta(days=assigned_days_ago),
                )
            )
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
            if (
                quiet_after_days is not None
            ):  # chatty for three weeks, then silent: a welfare case
                s.flush()
                family = s.execute(
                    select(Contact.id).where(
                        Contact.resident_id == r.id, Contact.type == "family"
                    )
                ).scalar()
                for d in range(quiet_after_days, quiet_after_days + 20):
                    for k in range(2):
                        started = now - timedelta(days=d, hours=k)
                        s.add(
                            CallRecord(
                                resident_id=r.id,
                                contact_id=family,
                                contact_type="family",
                                privileged=False,
                                monitored=True,
                                provider_ref="seed",
                                started_at=started,
                                ended_at=started + timedelta(minutes=5),
                                max_seconds=900,
                                duration_seconds=300,
                                status="completed",
                            )
                        )
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
        resident("jo")  # staff e2e: sanction -> confirmation -> appeal -> overturn
        resident(
            "kim"
        )  # staff e2e: supervisor-issued sanction; staff-controlled settings
        # One officer who records far more than peers, so the outlier view has something to flag
        resident("zed")
        # Welfare: on the unit 40 days, talked twice a day until eight days ago, then nothing
        resident("wes", contacts=("family",), assigned_days_ago=40, quiet_after_days=8)
        resident(
            "tess", start_points=450, contacts=("family", "attorney")
        )  # tier 4: texting, reading
        resident("vic", start_points=1000, contacts=("family",))  # tier 6: video
        resident("ned")  # education e2e: first course, certificate
        resident("pam")  # education e2e: offline mid-lesson
        resident("cam")  # receives a cell-camera event
        resident("wren")  # tier 1: voluntary work, earnings
        resident("uma", unit="B")  # unit B: schedule and out-of-cell tests
        resident("val", unit="B")
        resident(
            "ola", start_points=450, contacts=("family", "attorney")
        )  # tier 4: monitored texting and the keyword-flag review
        resident(
            "nia", start_points=450
        )  # tier 4, no contacts yet: contact-request flow
        resident(
            "rae", start_points=1000, contacts=("family", "attorney")
        )  # tier 6: video calls, scheduling, tamper in the browser
        resident(
            "lee", start_points=450
        )  # tier 4, then a confirmed CAM_BLOCK: reading locks
        heavy = Actor(
            s.execute(select(Staff.id).where(Staff.username == "e2e_heavy")).scalar(),
            "officer",
        )
        zed_id = s.execute(
            select(Resident.id).where(Resident.code == "E2E-ZED")
        ).scalar()
        for i in range(8):
            sanctions.issue_sanction(
                s, heavy, zed_id, "CELL_MESS", now - timedelta(minutes=10 + i)
            )

        def staff_actor(username, role):
            return Actor(
                s.execute(select(Staff.id).where(Staff.username == username)).scalar(),
                role,
            )

        lee_id = s.execute(
            select(Resident.id).where(Resident.code == "E2E-LEE")
        ).scalar()
        lock = sanctions.issue_sanction(
            s,
            staff_actor("e2e_officer", "officer"),
            lee_id,
            "CAM_BLOCK",
            now - timedelta(hours=2),
            Evidence(
                "second_staff_report",
                reporter_id=staff_actor("e2e_colleague", "officer").id,
            ),
        )
        sanctions.confirm_sanction(
            s, staff_actor("e2e_sup1", "supervisor"), lock.id, now - timedelta(hours=1)
        )
    fixtures = {
        "tokens": tokens,
        "staff": STAFF,
        "staff_password": STAFF_PASSWORD,
        "generated_at": now.isoformat(),
    }
    OUT.write_text(json.dumps(fixtures, indent=2))
    print(f"e2e database {DB} ready; fixtures -> {OUT}")


if __name__ == "__main__":
    sys.exit(main())
