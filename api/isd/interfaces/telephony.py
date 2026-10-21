"""Telephony boundary (invariant 10) and the attorney-privilege guard (invariant 6).

Providers only ever see an opaque phone reference, never the resident or contact identity.
`TelephonyService` is the only way app code reaches a provider. For a privileged (attorney)
call it tells the provider not to record, never asks for monitoring data, and refuses to
hand back a recording, transcript, or monitoring reference, even if a provider misbehaves.
"""

from dataclasses import dataclass
from typing import Protocol


class PrivilegedCommunicationError(RuntimeError):
    """Raised on any attempt to capture or read privileged communication content."""


@dataclass(frozen=True)
class CallHandle:
    provider_ref: str
    privileged: bool


class TelephonyProvider(Protocol):
    def start_call(self, phone_ref: str, *, record: bool, max_seconds: int) -> str:
        """Returns the provider's call reference."""

    def end_call(self, provider_ref: str) -> None: ...

    def monitoring_ref(self, provider_ref: str) -> str | None:
        """Reference to captured content for a monitored call, or None."""

    def read_recording(self, provider_ref: str) -> bytes: ...


class TelephonyService:
    def __init__(self, provider: TelephonyProvider):
        self._p = provider

    def place_call(self, phone_ref: str, *, privileged: bool, max_seconds: int) -> CallHandle:
        ref = self._p.start_call(phone_ref, record=not privileged, max_seconds=max_seconds)
        if privileged and self._p.monitoring_ref(ref) is not None:
            self._p.end_call(ref)  # provider captured content anyway: hang up and fail loudly
            raise PrivilegedCommunicationError("provider captured a privileged call")
        return CallHandle(ref, privileged)

    def end_call(self, handle: CallHandle) -> str | None:
        """Ends the call; returns a monitoring reference for monitored calls only."""
        self._p.end_call(handle.provider_ref)
        if handle.privileged:
            return None
        return self._p.monitoring_ref(handle.provider_ref)

    def recording(self, handle: CallHandle) -> bytes:
        if handle.privileged:
            raise PrivilegedCommunicationError("privileged calls have no recording")
        return self._p.read_recording(handle.provider_ref)
