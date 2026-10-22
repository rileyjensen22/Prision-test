"""Check that every balance matches its append-only ledger (invariant 15). Exit 2 on a mismatch.

The daily job runs this too. Run it on its own to re-check after a correction:
  .venv/bin/python scripts/reconcile.py
"""

import json
import sys
from datetime import UTC, datetime

from isd import settings
from isd.services.reconcile import reconcile
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def main() -> int:
    with (
        Session(create_engine(settings.MIGRATION_DATABASE_URL)) as session,
        session.begin(),
    ):
        result = reconcile(session, datetime.now(UTC))
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
