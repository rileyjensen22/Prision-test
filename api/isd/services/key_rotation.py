"""Re-encrypts every encrypted column with the active key (see isd/crypto.py).

Steps for a rotation: generate a new key, add it to `ENCRYPTION_KEYS` next to the old one, set
`ENCRYPTION_ACTIVE_KEY_ID` to the new id, restart the API, run `scripts/rotate-encryption-key.py`,
check it reports nothing left to rotate, then remove the old key. Rows are updated in batches and
the job is safe to repeat or to stop part-way: every value is readable with either key throughout.
"""

from sqlalchemy import text
from sqlalchemy.orm import Session

from isd import crypto

# (table, column, purpose): the one list of encrypted columns. A test checks it matches the models.
ENCRYPTED_COLUMNS = (
    ("contacts", "phone_ref", "contacts.phone_ref"),
    ("messages", "body", "messages.body"),
    ("call_records", "provider_ref", "call_records.provider_ref"),
    ("call_records", "monitor_ref", "call_records.monitor_ref"),
    ("staff", "mfa_secret", "staff.mfa_secret"),
)


def pending(session: Session) -> dict[str, int]:
    """Rows per column that are plain text or use a key other than the active one."""
    active = crypto.keyring()[1]
    out = {}
    for table, column, _ in ENCRYPTED_COLUMNS:
        n = session.execute(
            text(
                f"SELECT count(*) FROM {table} WHERE {column} IS NOT NULL "  # noqa: S608
                f"AND {column} NOT LIKE :p"
            ),
            {"p": f"{crypto.PREFIX}{active}:%"},
        ).scalar()
        out[f"{table}.{column}"] = n
    return out


def rotate_all(session: Session, batch: int = 500) -> dict[str, int]:
    """Re-encrypts what `pending` reports. Returns rows rotated per column."""
    active = crypto.keyring()[1]
    done: dict[str, int] = {}
    for table, column, purpose in ENCRYPTED_COLUMNS:
        total = 0
        while True:
            rows = session.execute(
                text(
                    f"SELECT id, {column} FROM {table} WHERE {column} IS NOT NULL "  # noqa: S608
                    f"AND {column} NOT LIKE :p ORDER BY id LIMIT :n"
                ),
                {"p": f"{crypto.PREFIX}{active}:%", "n": batch},
            ).all()
            if not rows:
                break
            for row_id, value in rows:
                session.execute(
                    text(f"UPDATE {table} SET {column} = :v WHERE id = :id"),  # noqa: S608
                    {"v": crypto.encrypt(crypto.decrypt(value, purpose), purpose), "id": row_id},
                )
            session.flush()
            total += len(rows)
        done[f"{table}.{column}"] = total
    return done
