"""Chess (stub): engine and human opponents behind ChessProvider. Moves only; there is no chat."""

import re
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from isd.interfaces.chess import ChessProvider
from isd.models import ChessGame, ChessMove, Resident
from isd.providers import get_chess
from isd.services.entitlement_service import get_entitlements

_MOVE = re.compile(r"^[a-h][1-8][a-h][1-8][qrbn]?$")  # coordinate form, for example e2e4
_FEATURE = {"engine": "chess_engine", "human": "chess_human"}


class ChessDenied(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def new_game(
    session: Session,
    resident_id: int,
    opponent: str,
    now: datetime,
    provider: ChessProvider | None = None,
):
    if opponent not in _FEATURE:
        raise ChessDenied("BAD_OPPONENT", "opponent must be engine or human")
    if not get_entitlements(session, resident_id, now).features[_FEATURE[opponent]].allowed:
        raise ChessDenied("FEATURE_LOCKED", "this kind of game is locked")
    code = session.get(Resident, resident_id).code
    made = (provider or get_chess()).new_game(code, opponent)
    game = ChessGame(
        resident_id=resident_id,
        opponent_kind=opponent,
        status=made.status,
        provider_ref=made.provider_ref,
        created_at=now,
    )
    session.add(game)
    session.flush()
    return game


def moves(session: Session, game_id: int) -> list[ChessMove]:
    return list(
        session.execute(
            select(ChessMove).where(ChessMove.game_id == game_id).order_by(ChessMove.ply)
        ).scalars()
    )


def play(
    session: Session,
    resident_id: int,
    game_id: int,
    move: str,
    now: datetime,
    provider: ChessProvider | None = None,
):
    game = session.get(ChessGame, game_id)
    if game is None or game.resident_id != resident_id:
        raise ChessDenied("NOT_FOUND", "game not found")
    if game.status != "active":
        raise ChessDenied("NOT_ACTIVE", "this game is not active")
    # Re-check on every move: a sanction or tier change takes effect mid-game.
    if (
        not get_entitlements(session, resident_id, now)
        .features[_FEATURE[game.opponent_kind]]
        .allowed
    ):
        raise ChessDenied("FEATURE_LOCKED", "this kind of game is locked")
    if not _MOVE.match(move):
        raise ChessDenied("BAD_MOVE", "write the move like e2e4")
    ply = len(moves(session, game_id)) + 1
    session.add(ChessMove(game_id=game_id, ply=ply, move=move, by="resident", at=now))
    reply = (provider or get_chess()).submit_move(game.provider_ref, move, ply)
    if reply:
        session.add(ChessMove(game_id=game_id, ply=ply + 1, move=reply, by="opponent", at=now))
    session.flush()
    return moves(session, game_id)
