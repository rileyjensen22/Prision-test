import uuid


class MockVideoProvider:
    """A demo provider: the kiosk loops the camera back to itself with WebRTC, so no media or
    network is involved here. Records only when told to (and the recording is just a marker)."""

    def __init__(self, ignore_no_record: bool = False):
        self.sessions: dict[str, dict] = {}
        self.deleted: list[str] = []
        self._ignore = ignore_no_record  # test hook: simulates a misbehaving provider

    def start_session(self, phone_ref: str, *, record: bool, max_seconds: int) -> str:
        ref = f"mockvid-{uuid.uuid4().hex[:12]}"
        self.sessions[ref] = {
            "phone_ref": phone_ref,
            "max_seconds": max_seconds,
            "recording": f"rec-{ref}" if (record or self._ignore) else None,
            "ended": False,
        }
        return ref

    def connection_info(self, provider_ref: str) -> dict:
        return {"mode": "loopback"}

    def end_session(self, provider_ref: str) -> None:
        self.sessions[provider_ref]["ended"] = True

    def recording_ref(self, provider_ref: str) -> str | None:
        return self.sessions[provider_ref]["recording"]

    def delete_recording(self, provider_ref: str) -> None:
        self.sessions[provider_ref]["recording"] = None
        self.deleted.append(provider_ref)
