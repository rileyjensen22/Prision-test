"""Back up a database, restore it somewhere else, and prove the copy is whole and still safe.

    python scripts/backup-restore-drill.py [--source-db NAME] [--report docs/backup-drill.md]

Steps: dump, restore into a scratch database, then check that (1) every table has the same number of
rows, (2) the audit hash chain still verifies, (3) the ledgers still reconcile, (4) the append-only
protections came back (triggers refuse UPDATE; the app role has no UPDATE or DELETE grant on the
protected tables), and (5) the schema version matches. Exit code 0 only if all pass. The scratch
database is dropped at the end. Timings are printed so the recovery time is a measurement, not a guess.
"""

import argparse
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

from isd import settings
from isd.services.audit import verify_chain
from isd.services.reconcile import reconcile
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parent))
import backup

PROTECTED = (
    "audit_log", "config_versions", "trust_ledger", "out_of_cell_log", "earnings_ledger",
    "work_log", "reconciliation_runs", "task_submissions", "out_of_cell_events", "certificates",
    "reentry_events", "outcome_records",
)  # fmt: skip


def url_for(db: str) -> str:
    return (
        make_url(settings.MIGRATION_DATABASE_URL)
        .set(database=db)
        .render_as_string(False)
    )


def row_counts(url: str) -> dict[str, int]:
    eng = create_engine(url)
    with eng.connect() as c:
        tables = (
            c.execute(
                text(
                    "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY 1"
                )
            )
            .scalars()
            .all()
        )
        counts = {
            t: c.execute(text(f'SELECT count(*) FROM "{t}"')).scalar() for t in tables
        }
    eng.dispose()
    return counts


def restore(dump_file: Path, scratch: str) -> float:
    admin = create_engine(url_for("postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f"DROP DATABASE IF EXISTS {scratch} WITH (FORCE)"))
        c.execute(text(f"CREATE DATABASE {scratch}"))
    admin.dispose()
    env, conn = backup.pg_env()
    started = time.time()
    subprocess.run(
        ["pg_restore", *conn, "--no-password", "--exit-on-error", "-d", scratch, str(dump_file)],
        env=env, check=True,
    )  # fmt: skip
    return time.time() - started


def checks(source: str, scratch: str) -> list[tuple[str, bool, str]]:
    out: list[tuple[str, bool, str]] = []
    a, b = row_counts(url_for(source)), row_counts(url_for(scratch))
    diff = {t: (a.get(t), b.get(t)) for t in set(a) | set(b) if a.get(t) != b.get(t)}
    out.append(
        (
            "every table has the same number of rows",
            not diff,
            f"{len(a)} tables, {sum(a.values())} rows" if not diff else str(diff),
        )
    )
    eng = create_engine(url_for(scratch))
    with Session(eng) as s:
        chain = verify_chain(s)
        out.append(
            (
                "audit chain verifies in the restored copy",
                chain.ok,
                f"{chain.entries} entries",
            )
        )
        rec = reconcile(s, datetime.now(UTC))
        s.commit()
        out.append(("ledgers reconcile in the restored copy", bool(rec["ok"]), ""))
        try:
            with s.begin_nested():
                s.execute(text("UPDATE audit_log SET action = 'x'"))
            refused = False  # the UPDATE went through: the protection did not come back
        except Exception:  # noqa: BLE001 - the trigger is supposed to refuse
            refused = True
        s.rollback()
        out.append(("append-only trigger came back (UPDATE refused)", refused, ""))
        leaks = [
            t for t in PROTECTED
            if s.execute(text("SELECT has_table_privilege('isd_app', :t, 'UPDATE') OR has_table_privilege('isd_app', :t, 'DELETE')"), {"t": t}).scalar()
        ]  # fmt: skip
        out.append(
            (
                "app role still cannot UPDATE or DELETE protected tables",
                not leaks,
                str(leaks) if leaks else f"{len(PROTECTED)} tables",
            )
        )
        v_src = (
            create_engine(url_for(source))
            .connect()
            .execute(text("SELECT version_num FROM alembic_version"))
            .scalar()
        )
        v_new = s.execute(text("SELECT version_num FROM alembic_version")).scalar()
        out.append(("schema version matches", v_src == v_new, f"{v_new}"))
    eng.dispose()
    return out


def write_report(
    path: Path, source: str, size: int, t_dump: float, t_restore: float, results
) -> None:
    ok = all(r[1] for r in results)
    lines = [
        "# Backup and restore drill: latest result",
        "",
        "Written by `scripts/backup-restore-drill.py`. Re-run it to refresh this file.",
        "",
        f"- Date: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}",
        f"- Source: database `{source}` (synthetic data only)",
        f"- Dump size: {size / 1024:.0f} KiB; dump took {t_dump:.1f} s; restore took {t_restore:.1f} s",
        f"- Result: **{'PASS' if ok else 'FAIL'}**",
        "",
        "| Check | Result | Detail |",
        "|---|---|---|",
        *[f"| {n} | {'pass' if p else 'FAIL'} | {d} |" for n, p, d in results],
        "",
        "Timings come from a small synthetic database on one machine. They show the procedure works, not",
        "how long a real facility's restore will take; repeat the drill on a production-sized copy.",
        "",
    ]
    path.write_text("\n".join(lines))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--source-db", default=make_url(settings.MIGRATION_DATABASE_URL).database
    )
    ap.add_argument("--scratch-db", default="isd_restore_drill")
    ap.add_argument("--report", type=Path)
    args = ap.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        dump_file, t_dump = backup.dump(Path(tmp), args.source_db)
        if not backup.verify_checksum(dump_file):
            print("FAIL: checksum does not match the dump")
            return 1
        t_restore = restore(dump_file, args.scratch_db)
        size = dump_file.stat().st_size
    try:
        results = checks(args.source_db, args.scratch_db)
    finally:
        admin = create_engine(url_for("postgres"), isolation_level="AUTOCOMMIT")
        with admin.connect() as c:
            c.execute(text(f"DROP DATABASE IF EXISTS {args.scratch_db} WITH (FORCE)"))
        admin.dispose()
    for name, passed, detail in results:
        print(
            f"  [{'PASS' if passed else 'FAIL'}] {name}"
            + (f"  ({detail})" if detail else "")
        )
    print(f"dump {t_dump:.1f}s, restore {t_restore:.1f}s, {size} bytes")
    if args.report:
        write_report(args.report, args.source_db, size, t_dump, t_restore, results)
    ok = all(r[1] for r in results)
    print("DRILL PASSED" if ok else "DRILL FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
