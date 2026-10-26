"""Re-encrypt every encrypted column with the active key. See api/isd/services/key_rotation.py.

    ENCRYPTION_KEYS="old:<b64>,new:<b64>" ENCRYPTION_ACTIVE_KEY_ID=new python scripts/rotate-encryption-key.py

Prints how many values were rotated and how many remain (should be 0). Remove the old key only
after that.
"""

import sys

from isd import settings
from isd.services import key_rotation
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def main() -> int:
    engine = create_engine(settings.MIGRATION_DATABASE_URL)
    with Session(engine) as s, s.begin():
        done = key_rotation.rotate_all(s)
        left = key_rotation.pending(s)
    for name, n in done.items():
        print(f"{name:32} rotated {n}")
    remaining = sum(left.values())
    print(f"remaining: {remaining}")
    return 0 if remaining == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
