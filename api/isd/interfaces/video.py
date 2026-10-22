"""Video boundary (invariant 10) with the same attorney-privilege guard as telephony (invariant 6).

The media itself is peer-to-peer WebRTC between the device and the other party, so no video frame
passes through this app (invariant 14). This interface only manages the call session: starting it,
ending it, and, for monitored calls when the operator enables it, a provider-side recording that
can later be deleted when its retention period ends. A privileged (attorney) video call is never
recorded; if a provider records one anyway, the call is ended and the call fails loudly.
"""

from dataclasses import dataclass
from typing import Protocol

from isd.interfaces.telephony import PrivilegedCommunicationError


@dataclass(frozen=True)
class VideoHandle:
    provider_ref: str
    privileged: bool
    connection: dict  # for the device, e.g. {"mode": "loopback"}


class VideoProvider(Protocol):
    def start_session(self, phone_ref: str, *, record: bool, max_seconds: int) -> str: ...

    def connection_info(self, provider_ref: str) -> dict: ...

    def end_session(self, provider_ref: str) -> None: ...

    def recording_ref(self, provider_ref: str) -> str | None:
        """Reference to a recording of the session, if the provider made one."""

    def delete_recording(self, provider_ref: str) -> None: ...


class VideoService:
    def __init__(self, provider: VideoProvider):
        self._p = provider

    def place(
        self, phone_ref: str, *, privileged: bool, record: bool, max_seconds: int
    ) -> VideoHandle:
        ref = self._p.start_session(
            phone_ref, record=record and not privileged, max_seconds=max_seconds
        )
        if privileged and self._p.recording_ref(ref) is not None:
            self._p.end_session(ref)
            raise PrivilegedCommunicationError("provider recorded a privileged video call")
        return VideoHandle(ref, privileged, self._p.connection_info(ref))

    def end(self, handle: VideoHandle) -> str | None:
        """Ends the session; returns a recording reference for monitored calls only."""
        self._p.end_session(handle.provider_ref)
        return None if handle.privileged else self._p.recording_ref(handle.provider_ref)

    def purge(self, provider_ref: str) -> None:
        self._p.delete_recording(provider_ref)
