import uuid


class MockMessagingProvider:
    """In-memory messaging. Keeps a monitoring copy only when told to retain."""

    def __init__(self, ignore_no_retain: bool = False):
        self.copies: dict[str, str | None] = {}
        self.states: dict[str, str] = {}
        self._ignore = ignore_no_retain  # test hook: simulates a misbehaving provider

    def send(self, phone_ref: str, body: str, *, retain: bool) -> tuple[str, str | None]:
        ref = f"mockmsg-{uuid.uuid4().hex[:12]}"
        keep = retain or self._ignore
        self.copies[ref] = body if keep else None
        # synthetic numbers containing FAIL simulate an undeliverable message
        self.states[ref] = "failed" if "FAIL" in phone_ref.upper() else "delivered"
        return ref, ("Got your message. (mock reply)" if retain else None)

    def delivery_state(self, provider_ref: str) -> str:
        return self.states[provider_ref]

    def retained_copy(self, provider_ref: str) -> str | None:
        return self.copies[provider_ref]
