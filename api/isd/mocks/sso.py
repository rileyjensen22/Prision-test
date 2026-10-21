class MockSSOProvider:
    """Accepts 'mock:<username>'. Development only; production settings forbid it."""

    def subject_for(self, assertion: str) -> str | None:
        prefix, _, name = assertion.partition(":")
        return name if prefix == "mock" and name else None
