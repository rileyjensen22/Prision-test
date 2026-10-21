"""Write the public sanctions log as static files. Refuses to run unless an operator has enabled it.

Usage: python scripts/export-public-log.py [--out var/public-log]
Exit codes: 0 written, 2 disabled by the operator.
"""

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

from isd import settings
from isd.services.public_log import PublicLogDisabled, export
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "var" / "public-log"))
    args = ap.parse_args()
    if settings.PUBLIC_LOG_SALT.startswith("dev-only"):
        print(
            "warning: using the development pseudonym salt; set PUBLIC_LOG_SALT for a real export"
        )
    with (
        Session(create_engine(settings.MIGRATION_DATABASE_URL)) as session,
        session.begin(),
    ):
        try:
            result = export(
                session, datetime.now(UTC), settings.PUBLIC_LOG_SALT, Path(args.out)
            )
        except PublicLogDisabled as e:
            print(f"not exported: {e}")
            return 2
    print(
        f"exported {result['records']} records to {result['dir']}: {', '.join(result['files'])}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
