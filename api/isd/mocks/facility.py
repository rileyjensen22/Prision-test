from isd.interfaces.facility import FacilityEventIn


class MockFacilityEventSource:
    """Holds events a test or a staff 'simulate' action pushed in."""

    def __init__(self) -> None:
        self._queue: list[FacilityEventIn] = []

    def push(self, event: FacilityEventIn) -> None:
        self._queue.append(event)

    def poll(self) -> list[FacilityEventIn]:
        out, self._queue = self._queue, []
        return out
