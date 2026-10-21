import uuid

from isd.interfaces.chess import NewGame

_ENGINE_REPLIES = [
    "e7e5",
    "g8f6",
    "b8c6",
    "f8c5",
    "d7d6",
    "c8e6",
]  # a fixed script, not a real engine


class MockChessProvider:
    def new_game(self, resident_ref: str, opponent: str) -> NewGame:
        ref = f"mockchess-{uuid.uuid4().hex[:10]}"
        return NewGame(ref, "active" if opponent == "engine" else "waiting")

    def submit_move(self, provider_ref: str, move: str, ply: int) -> str | None:
        if provider_ref.startswith("mockchess-") and ply % 2 == 1:
            return _ENGINE_REPLIES[(ply // 2) % len(_ENGINE_REPLIES)]
        return None
