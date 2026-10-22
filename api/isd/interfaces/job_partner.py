"""Work-partner boundary (invariant 10). A partner supplies tasks and reviews the answers.
v1 only has a mock; a real partner would also have to meet the content rules in
`isd.work_rules` (public or synthetic material only, never anyone's personal data)."""

from typing import Protocol

from isd.work_rules import Review


class JobPartner(Protocol):
    code: str
    name: str

    def fetch_tasks(self, kind: str, count: int, offset: int) -> list[dict]:
        """Up to `count` task specs, each with a stable `external_id`, starting at `offset`."""

    def review(self, kind: str, spec: dict, answer: str, min_similarity: float) -> Review: ...
