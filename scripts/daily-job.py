"""Run the daily job for yesterday. Schedule it once a day shortly after midnight (UTC).

10 0 * * *  cd /srv/isd && .venv/bin/python scripts/daily-job.py
"""

import json
import sys
from datetime import UTC, datetime

from isd import settings
from isd.services.daily import run_daily
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def main() -> int:
    with (
        Session(create_engine(settings.MIGRATION_DATABASE_URL)) as session,
        session.begin(),
    ):
        result = run_daily(session, datetime.now(UTC))
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
