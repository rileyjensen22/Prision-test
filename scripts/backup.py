"""Take a database backup: a compressed pg_dump with a checksum, keeping the newest N.

    python scripts/backup.py DEST_DIR [--keep 14] [--db NAME]

Uses MIGRATION_DATABASE_URL (the owner). The password goes to pg_dump through the environment, not
the command line. Files are readable only by the owner. Backups contain resident records: store
them as carefully as the database itself (encrypted disk or encrypted copy; see docs/operations.md).
"""

import argparse
import hashlib
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from isd import settings
from sqlalchemy.engine import make_url


def pg_env() -> tuple[dict[str, str], list[str]]:
    url = make_url(settings.MIGRATION_DATABASE_URL)
    env = {**os.environ, "PGPASSWORD": url.password or ""}
    args = [
        "-h",
        url.host or "localhost",
        "-p",
        str(url.port or 5432),
        "-U",
        url.username or "",
    ]
    return env, args


def dump(
    dest: Path, db: str | None = None, stamp: str | None = None
) -> tuple[Path, float]:
    url = make_url(settings.MIGRATION_DATABASE_URL)
    name = db or url.database
    dest.mkdir(parents=True, exist_ok=True)
    stamp = stamp or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out = dest / f"isd-{name}-{stamp}.dump"
    env, conn = pg_env()
    started = time.time()
    subprocess.run(
        ["pg_dump", *conn, "-Fc", "--no-password", "-f", str(out), name],
        env=env,
        check=True,
    )
    out.chmod(0o600)
    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    (dest / (out.name + ".sha256")).write_text(f"{digest}  {out.name}\n")
    return out, time.time() - started


def prune(dest: Path, keep: int) -> list[Path]:
    dumps = sorted(dest.glob("isd-*.dump"))
    gone = dumps[:-keep] if keep > 0 else []
    for d in gone:
        d.unlink()
        (dest / (d.name + ".sha256")).unlink(missing_ok=True)
    return gone


def verify_checksum(dump_file: Path) -> bool:
    line = (dump_file.parent / (dump_file.name + ".sha256")).read_text().split()
    return line[0] == hashlib.sha256(dump_file.read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("dest", type=Path)
    ap.add_argument("--keep", type=int, default=14)
    ap.add_argument("--db")
    args = ap.parse_args()
    out, secs = dump(args.dest, args.db)
    pruned = prune(args.dest, args.keep)
    print(
        f"wrote {out} ({out.stat().st_size} bytes, {secs:.1f}s); pruned {len(pruned)} old backup(s)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
