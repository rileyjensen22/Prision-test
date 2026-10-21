"""Run a deterministic week of synthetic activity and check the system's invariants.

    python scripts/simulate-week.py [--residents 24] [--days 7] [--seed 1]

Uses a throwaway database (isd_sim, dropped and recreated). Exit code 0 means every check passed;
the full report is written to var/simulate-week-report.json.
"""

import argparse
import os
import sys
import time
from pathlib import Path

from alembic import command
from alembic.config import Config
from isd import settings
from isd.simulation import SimConfig, run_simulation, write_report
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
DB = os.environ.get("SIM_DB", "isd_sim")


def fresh_database() -> str:
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
    return url


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--residents", type=int, default=24)
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()

    started = time.time()
    print(
        f"Creating a fresh {DB} database and running {args.days} days with {args.residents} residents..."
    )
    engine = create_engine(fresh_database())
    report = run_simulation(
        engine, SimConfig(seed=args.seed, residents=args.residents, days=args.days)
    )
    write_report(report, ROOT / "var" / "simulate-week-report.json")

    print(
        f"\nActions: {sum(report.counts.values())} done, {sum(report.denied.values())} refused by the rules"
    )
    for name, n in sorted(report.counts.items()):
        print(f"  {name:<18}{n}")
    print("\nChecks:")
    for c in report.checks:
        print(
            f"  [{'PASS' if c.passed else 'FAIL'}] {c.name}"
            + (f"  ({c.detail})" if c.detail else "")
        )
    print(f"\nSummary: {report.summary}")
    print(
        f"\n{'ALL CHECKS PASSED' if report.passed else 'CHECKS FAILED'} in {time.time() - started:.0f}s"
    )
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
