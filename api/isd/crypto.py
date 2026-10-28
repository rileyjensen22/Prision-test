"""Encryption at rest for the few columns that hold sensitive content: message bodies, contact
numbers, call recording references and the staff MFA secret.

AES-256-GCM, one random nonce per value. A stored value looks like `enc1:<key id>:<base64>`; the key
id says which key to decrypt with, so keys can be rotated: add a new key, make it active, run
`scripts/rotate-encryption-key.py`, and retire the old key once nothing uses it. Each value is bound
to a purpose string (for example `messages.body`) so ciphertext cannot be moved to another column.
A value without the `enc1:` prefix is treated as plain text, which lets old rows be read until the
rotation script has encrypted them.

Keys come from the environment (`ENCRYPTION_KEYS`), never from the database. In development, when no
keys are set, a fixed development key is used; production refuses to start without real keys.
"""

import base64
import hashlib
import hmac
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy.types import Text, TypeDecorator

from isd import settings

PREFIX = "enc1:"
_DEV_KEY_ID = "dev1"
_DEV_KEY = hashlib.sha256(b"isd-development-encryption-key").digest()


class CryptoError(ValueError):
    pass


def _parse(raw: str) -> dict[str, bytes]:
    keys: dict[str, bytes] = {}
    for part in filter(None, (p.strip() for p in raw.split(","))):
        kid, _, b64 = part.partition(":")
        key = base64.b64decode(b64)
        if not kid or len(key) != 32:
            raise CryptoError("each encryption key must be 'id:base64' with 32 bytes")
        keys[kid] = key
    return keys


def keyring() -> tuple[dict[str, bytes], str]:
    """(all keys by id, active key id), read fresh so tests and rotation can change them."""
    raw = os.environ.get("ENCRYPTION_KEYS", settings.ENCRYPTION_KEYS)
    active = os.environ.get("ENCRYPTION_ACTIVE_KEY_ID", settings.ENCRYPTION_ACTIVE_KEY_ID)
    if not raw.strip():
        if settings.ENV == "production":
            raise CryptoError("ENCRYPTION_KEYS is not set")
        return {_DEV_KEY_ID: _DEV_KEY}, _DEV_KEY_ID
    keys = _parse(raw)
    active = active or next(iter(keys))
    if active not in keys:
        raise CryptoError("ENCRYPTION_ACTIVE_KEY_ID is not in ENCRYPTION_KEYS")
    return keys, active


def is_encrypted(value: str | None) -> bool:
    return bool(value) and value.startswith(PREFIX)


def key_id_of(value: str) -> str | None:
    return value.split(":", 2)[1] if is_encrypted(value) else None


def encrypt(plain: str, purpose: str) -> str:
    keys, active = keyring()
    nonce = os.urandom(12)
    blob = AESGCM(keys[active]).encrypt(nonce, plain.encode(), purpose.encode())
    return f"{PREFIX}{active}:{base64.urlsafe_b64encode(nonce + blob).decode()}"


def decrypt(value: str, purpose: str) -> str:
    if not is_encrypted(value):
        return value  # legacy plain text, until the rotation script has run
    _, kid, b64 = value.split(":", 2)
    keys, _ = keyring()
    if kid not in keys:
        raise CryptoError(f"no key '{kid}' to decrypt with")
    raw = base64.urlsafe_b64decode(b64)
    try:
        return AESGCM(keys[kid]).decrypt(raw[:12], raw[12:], purpose.encode()).decode()
    except InvalidTag as e:
        raise CryptoError("value was changed, or belongs to another column") from e


def needs_rotation(value: str | None) -> bool:
    """True for plain text, or text encrypted with a key that is no longer the active one."""
    if value is None:
        return False
    return key_id_of(value) != keyring()[1]


def blind_index(plain: str) -> str:
    """A keyed hash for exact-match lookups (duplicate contact numbers) without decrypting."""
    key = os.environ.get("BLIND_INDEX_KEY", settings.BLIND_INDEX_KEY).encode()
    return hmac.new(key, plain.strip().encode(), hashlib.sha256).hexdigest()


class EncryptedText(TypeDecorator):
    """A text column stored encrypted. Reads decrypt, writes encrypt; the rest of the app sees
    ordinary strings. Equality queries on the column do not work (use a blind index)."""

    impl = Text
    cache_ok = True

    def __init__(self, purpose: str):
        super().__init__()
        self.purpose = purpose

    def process_bind_param(self, value, dialect):
        if value is None or is_encrypted(value):
            return value
        return encrypt(value, self.purpose)

    def process_result_value(self, value, dialect):
        return None if value is None else decrypt(value, self.purpose)
