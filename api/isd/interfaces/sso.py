"""Single sign-on boundary (CLAUDE.md section 5). A real identity provider plugs in here."""

from typing import Protocol


class SSOProvider(Protocol):
    def subject_for(self, assertion: str) -> str | None:
        """Validates an assertion from the identity provider; returns the staff username or None."""
