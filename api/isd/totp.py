"""Time-based one-time passwords (RFC 6238: SHA-1, 6 digits, 30 second steps), no extra library.

Compatible with common authenticator apps. A code is accepted for the current step or one step
either side (clock drift) and each step can be used only once (the caller stores the last step).
"""

import base64
import hashlib
import hmac
import os
import struct
from urllib.parse import quote

STEP = 30
DIGITS = 6
WINDOW = 1


def new_secret() -> str:
    return base64.b32encode(os.urandom(20)).decode().rstrip("=")


def _code(secret: str, step: int) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8))
    mac = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    offset = mac[-1] & 0x0F
    number = (struct.unpack(">I", mac[offset : offset + 4])[0] & 0x7FFFFFFF) % (10**DIGITS)
    return str(number).zfill(DIGITS)


def code_at(secret: str, unix_time: float) -> str:
    return _code(secret, int(unix_time // STEP))


def verify(secret: str, code: str, unix_time: float, last_step: int | None = None) -> int | None:
    """Returns the step the code belongs to if it is valid and not used before, else None."""
    code = "".join(c for c in code if c.isdigit())
    if len(code) != DIGITS:
        return None
    now_step = int(unix_time // STEP)
    for step in range(now_step - WINDOW, now_step + WINDOW + 1):
        if hmac.compare_digest(_code(secret, step), code) and (
            last_step is None or step > last_step
        ):
            return step
    return None


def provisioning_uri(secret: str, account: str, issuer: str = "ISD") -> str:
    return (
        f"otpauth://totp/{quote(issuer)}:{quote(account)}?secret={secret}"
        f"&issuer={quote(issuer)}&digits={DIGITS}&period={STEP}"
    )
