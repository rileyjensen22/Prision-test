"""Raise, escalate and clear welfare flags now. Schedule it every 15 minutes so a flag nobody has
handled reaches a supervisor on time even when nobody has the staff app open:

*/15 * * * *  cd /srv/isd && .venv/bin/python scripts/welfare-sweep.py
"""

import json
import sys
from datetime import UTC, datetime

from isd import settings
from isd.services.welfare import sync_flags
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def main() -> int:
    with (
        Session(create_engine(settings.MIGRATION_DATABASE_URL)) as session,
        session.begin(),
    ):
        result = sync_flags(session, datetime.now(UTC))
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
