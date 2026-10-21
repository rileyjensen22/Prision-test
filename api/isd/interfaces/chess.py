"""Chess boundary for a future partnership (invariant 10). Moves only; there is no chat."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class NewGame:
    provider_ref: str
    status: str  # active | waiting


class ChessProvider(Protocol):
    def new_game(self, resident_ref: str, opponent: str) -> NewGame: ...

    def submit_move(self, provider_ref: str, move: str, ply: int) -> str | None:
        """Returns the opponent's reply move, or None when there is none yet (human opponent)."""
