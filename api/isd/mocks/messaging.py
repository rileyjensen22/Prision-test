import uuid


class MockMessagingProvider:
    """In-memory messaging. Keeps a monitoring copy only when told to retain."""

    def __init__(self, ignore_no_retain: bool = False):
        self.copies: dict[str, str | None] = {}
        self._ignore = ignore_no_retain  # test hook: simulates a misbehaving provider

    def send(self, phone_ref: str, body: str, *, retain: bool) -> tuple[str, str | None]:
        ref = f"mockmsg-{uuid.uuid4().hex[:12]}"
        keep = retain or self._ignore
        self.copies[ref] = body if keep else None
        return ref, ("Got your message. (mock reply)" if retain else None)

    def retained_copy(self, provider_ref: str) -> str | None:
        return self.copies[provider_ref]
