"""Contact verification boundary (invariant 10). v1 only has a stub: a real deployment checks
phone numbers, and attorney contacts against a bar-number registry (see docs/ASSUMPTIONS.md)."""

from typing import Protocol


class ContactVerifier(Protocol):
    def verify(self, contact_type: str, phone_ref: str) -> str:
        """A short label recorded with the contact, such as 'stub_verified'."""
