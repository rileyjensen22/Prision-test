"""Contact request rules. Pure."""

import re

CONTACT_TYPES = ("family", "friend", "attorney")
_NUMBER = re.compile(r"^[0-9+()\-. ]{7,20}$")


class ContactInvalid(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def clean_request(name: str, kind: str, phone: str) -> tuple[str, str, str]:
    name, phone = " ".join(name.split()), phone.strip()
    if not 2 <= len(name) <= 64:
        raise ContactInvalid("BAD_NAME", "enter the person's name")
    if kind not in CONTACT_TYPES:
        raise ContactInvalid("BAD_TYPE", "choose family, friend or attorney")
    if not _NUMBER.match(phone) or sum(c.isdigit() for c in phone) < 7:
        raise ContactInvalid("BAD_NUMBER", "enter a phone number")
    return name, kind, phone


def can_review(role: str, contact_type: str) -> bool:
    """Officers handle family and friends. Attorney contacts (privileged) need a supervisor."""
    if role in ("supervisor", "admin"):
        return True
    return role == "officer" and contact_type != "attorney"
