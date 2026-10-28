"""Password rules for staff accounts."""

import secrets

MIN_LENGTH = 12
_COMMON = {
    "password1234", "passwordpassword", "123456789012", "qwertyuiop12", "letmein123456",
    "administrator", "welcome12345", "changeme1234",
}  # fmt: skip


class WeakPassword(ValueError):
    pass


def check(new: str, username: str, current: str | None = None) -> None:
    if len(new) < MIN_LENGTH:
        raise WeakPassword(f"use at least {MIN_LENGTH} characters")
    if len(new) > 256:
        raise WeakPassword("that password is too long")
    low = new.lower()
    if low in _COMMON or username.lower() in low:
        raise WeakPassword("choose a password that is harder to guess, and not your username")
    if len(set(new)) < 5:
        raise WeakPassword("use a mix of different characters")
    if current is not None and new == current:
        raise WeakPassword("choose a new password, not your current one")


def temporary() -> str:
    """A one-time password handed to the person by an administrator; it must be changed at once."""
    return secrets.token_urlsafe(12)
