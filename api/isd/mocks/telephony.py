import uuid


class MockTelephonyProvider:
    """In-memory telephony. Never touches a network. Records only when told to."""

    def __init__(self, ignore_no_record: bool = False):
        self.calls: dict[str, dict] = {}
        self.recordings_created = 0
        self._ignore_no_record = ignore_no_record  # test hook: simulates a misbehaving provider

    def start_call(self, phone_ref: str, *, record: bool, max_seconds: int) -> str:
        ref = f"mockcall-{uuid.uuid4().hex[:12]}"
        capture = record or self._ignore_no_record
        self.calls[ref] = {
            "phone_ref": phone_ref,
            "max_seconds": max_seconds,
            "monitoring_ref": f"mon-{ref}" if capture else None,
            "audio": b"[synthetic audio]" if capture else None,
            "ended": False,
        }
        self.recordings_created += capture
        return ref

    def end_call(self, provider_ref: str) -> None:
        self.calls[provider_ref]["ended"] = True

    def monitoring_ref(self, provider_ref: str) -> str | None:
        return self.calls[provider_ref]["monitoring_ref"]

    def read_recording(self, provider_ref: str) -> bytes:
        audio = self.calls[provider_ref]["audio"]
        if audio is None:
            raise LookupError("no recording")
        return audio
