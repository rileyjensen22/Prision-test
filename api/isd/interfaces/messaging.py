"""Messaging boundary (invariant 10), with the attorney-privilege guard of telephony (invariant 6).

For a privileged (attorney) message the provider is told not to keep a copy, the guard checks that
it did not, and nothing is returned for storage.
"""

from dataclasses import dataclass
from typing import Protocol

from isd.interfaces.telephony import PrivilegedCommunicationError


@dataclass(frozen=True)
class Sent:
    provider_ref: str
    reply: str | None  # an inbound reply to store (monitored messages only)


class MessagingProvider(Protocol):
    def send(self, phone_ref: str, body: str, *, retain: bool) -> tuple[str, str | None]:
        """Returns (provider_ref, canned inbound reply or None)."""

    def retained_copy(self, provider_ref: str) -> str | None:
        """The provider's monitoring copy of the message, if it kept one."""


class MessagingService:
    def __init__(self, provider: MessagingProvider):
        self._p = provider

    def send(self, phone_ref: str, body: str, *, privileged: bool) -> Sent:
        ref, reply = self._p.send(phone_ref, body, retain=not privileged)
        if privileged:
            if self._p.retained_copy(ref) is not None:
                raise PrivilegedCommunicationError("provider kept a privileged message")
            return Sent(ref, None)  # nothing comes back for the app to store
        return Sent(ref, reply)
