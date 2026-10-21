"""How events from the facility's own systems (for example cell cameras) reach the app.

The software does not run cell cameras (CLAUDE.md section 9); it only receives their events.
"""

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class FacilityEventIn:
    event_id: str  # unique per source event; makes ingest idempotent
    type: str  # camera_obstruction | out_of_cell
    payload: dict = field(default_factory=dict)


class FacilityEventSource(Protocol):
    def poll(self) -> list[FacilityEventIn]: ...
