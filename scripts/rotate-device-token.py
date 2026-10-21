"""Issue a new random token for a kiosk (the old one stops working at once).

    python scripts/rotate-device-token.py DEVICE_CODE

Prints the token once. Give it to the device as  https://<host>/resident#device=<token>
The server keeps only a hash, so a lost token cannot be recovered; rotate again instead.
"""

import sys
from datetime import UTC, datetime

from isd import settings
from isd.services.audit import SYSTEM
from isd.services.devices import rotate_token
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    with (
        Session(create_engine(settings.MIGRATION_DATABASE_URL)) as session,
        session.begin(),
    ):
        try:
            token = rotate_token(session, SYSTEM, sys.argv[1], datetime.now(UTC))
        except LookupError as e:
            print(f"error: {e}")
            return 1
    print(
        f"New token for {sys.argv[1]} (shown once):\n  {token}\nKiosk address fragment:  #device={token}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
