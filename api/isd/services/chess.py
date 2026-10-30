"""Chess. Engine games are played on the device and only logged here. Human games are matches
between two residents: the server pairs them, checks every move against the rules, and keeps the
match log. The only things a resident can send are a move, a draw offer or answer, and resigning;
there is no chat, no spectator view and nothing to stake (invariant 13).

Residents see a random handle for the other player, never a name or a code.
"""

import random
from datetime import datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from isd.engine import chess_rules as rules
from isd.models import Cell, ChessGame, ChessMove, DeviceAssignment, KeepSeparate, Resident
from isd.services.config_store import get_current
from isd.services.entitlement_service import get_entitlements

DRAWN = {"agreed", "stalemate", "insufficient", "repetition", "seventy_five"}


class ChessDenied(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def settings(session: Session) -> dict:
    return get_current(session, "chess").payload


def levels(session: Session) -> list[dict]:
    return settings(session)["engine_levels"]


def _allowed(session: Session, resident_id: int, feature: str, now: datetime) -> bool:
    return get_entitlements(session, resident_id, now).features[feature].allowed


# ---------------- engine games (played on the device, logged here) ----------------
def new_engine_game(session: Session, resident_id: int, level: int, now: datetime) -> ChessGame:
    if not _allowed(session, resident_id, "chess", now):
        raise ChessDenied("FEATURE_LOCKED", "this kind of game is locked")
    if level not in {lv["level"] for lv in levels(session)}:
        raise ChessDenied("BAD_LEVEL", "unknown level")
    game = ChessGame(
        resident_id=resident_id,
        opponent_kind="engine",
        status="active",
        provider_ref="device-engine",
        level=level,
        created_at=now,
        updated_at=now,
    )
    session.add(game)
    session.flush()
    return game


def finish_engine_game(
    session: Session, resident_id: int, game_id: int, result: str, reason: str, now: datetime
) -> ChessGame:
    """Logs how a device game ended. The device is trusted for this: it is a log, not a ranking,
    and nothing earns points or changes a tier."""
    game = session.get(ChessGame, game_id)
    if game is None or game.resident_id != resident_id or game.opponent_kind != "engine":
        raise ChessDenied("NOT_FOUND", "game not found")
    if game.status == "finished":
        return game
    game.status, game.result, game.result_reason, game.updated_at = "finished", result, reason, now
    session.flush()
    return game


# ---------------- human matches ----------------
def _handle(session: Session, taken: set[str]) -> str:
    cfg = settings(session)
    rng = random.SystemRandom()
    while True:
        adjective, noun = rng.choice(cfg["handle_adjectives"]), rng.choice(cfg["handle_nouns"])
        h = f"{adjective} {noun} {rng.randrange(10, 100)}"
        if h not in taken:
            return h


def _line_of(session: Session, resident_id: int) -> str | None:
    return session.execute(
        select(Cell.line_code)
        .join(DeviceAssignment, DeviceAssignment.cell_id == Cell.id)
        .where(DeviceAssignment.resident_id == resident_id, DeviceAssignment.ended_at.is_(None))
    ).scalar()


def _kept_separate(session: Session, a: int, b: int) -> bool:
    lo, hi = sorted((a, b))
    return (
        session.execute(
            select(KeepSeparate.id).where(
                KeepSeparate.resident_a_id == lo,
                KeepSeparate.resident_b_id == hi,
                KeepSeparate.ended_at.is_(None),
            )
        ).first()
        is not None
    )


def may_pair(session: Session, a: int, b: int, now: datetime) -> bool:
    """Never two residents who must be kept apart, who live on the same line, or whose line is
    unknown, and both must be allowed to play humans right now."""
    if a == b or _kept_separate(session, a, b):
        return False
    line_a, line_b = _line_of(session, a), _line_of(session, b)
    if not line_a or not line_b or line_a == line_b:
        return False
    return _allowed(session, a, "chess_human", now) and _allowed(session, b, "chess_human", now)


def _open_match(session: Session, resident_id: int) -> ChessGame | None:
    return session.execute(
        select(ChessGame)
        .where(
            ChessGame.opponent_kind == "human",
            ChessGame.status.in_(("waiting", "active")),
            or_(ChessGame.resident_id == resident_id, ChessGame.black_resident_id == resident_id),
        )
        .order_by(ChessGame.id)
        .limit(1)
    ).scalar()


def _expire_waiting(session: Session, now: datetime) -> None:
    for g in session.execute(
        select(ChessGame)
        .where(
            ChessGame.opponent_kind == "human",
            ChessGame.status == "waiting",
            ChessGame.wait_until < now,
        )
        .with_for_update(skip_locked=True)
    ).scalars():
        g.status, g.result_reason, g.updated_at = "finished", "expired", now


def find_match(session: Session, resident_id: int, now: datetime) -> ChessGame:
    """Joins a waiting match if one fits, otherwise waits for an opponent."""
    if not _allowed(session, resident_id, "chess_human", now):
        raise ChessDenied("FEATURE_LOCKED", "this kind of game is locked")
    _expire_waiting(session, now)
    mine = _open_match(session, resident_id)
    if mine is not None:
        return mine
    waiting = session.execute(
        select(ChessGame)
        .where(
            ChessGame.opponent_kind == "human",
            ChessGame.status == "waiting",
            ChessGame.resident_id != resident_id,
        )
        .order_by(ChessGame.id)
        .with_for_update(skip_locked=True)
    ).scalars()
    for g in waiting:
        if may_pair(session, g.resident_id, resident_id, now):
            g.black_resident_id = resident_id
            g.black_handle = _handle(session, {g.white_handle or ""})
            g.status, g.fen, g.wait_until, g.updated_at = "active", rules.START_FEN, None, now
            session.flush()
            return g
    game = ChessGame(
        resident_id=resident_id,
        opponent_kind="human",
        status="waiting",
        provider_ref="local-match",
        white_handle=_handle(session, set()),
        created_at=now,
        updated_at=now,
        wait_until=now + timedelta(minutes=settings(session)["queue_minutes"]),
    )
    session.add(game)
    session.flush()
    return game


def _moves(session: Session, game_id: int) -> list[ChessMove]:
    return list(
        session.execute(
            select(ChessMove).where(ChessMove.game_id == game_id).order_by(ChessMove.ply)
        ).scalars()
    )


def _color(game: ChessGame, resident_id: int) -> str:
    if game.resident_id == resident_id:
        return "white"
    if game.black_resident_id == resident_id:
        return "black"
    raise ChessDenied("NOT_FOUND", "game not found")


def _mine(session: Session, resident_id: int, game_id: int, *, lock: bool = False) -> ChessGame:
    q = select(ChessGame).where(ChessGame.id == game_id, ChessGame.opponent_kind == "human")
    game = session.execute(q.with_for_update() if lock else q).scalar()
    if game is None:
        raise ChessDenied("NOT_FOUND", "game not found")
    _color(game, resident_id)
    return game


def _finish(game: ChessGame, result: str | None, reason: str, now: datetime) -> None:
    game.status, game.result, game.result_reason = "finished", result, reason
    game.draw_offer_by, game.updated_at = None, now


def play_move(
    session: Session, resident_id: int, game_id: int, text: str, now: datetime
) -> ChessGame:
    game = _mine(session, resident_id, game_id, lock=True)
    if game.status != "active":
        raise ChessDenied("NOT_ACTIVE", "this game is not active")
    # Re-checked on every move: a sanction or a staff switch takes effect mid-match.
    if not _allowed(session, resident_id, "chess_human", now):
        raise ChessDenied("FEATURE_LOCKED", "this kind of game is locked")
    _rate_check(session, resident_id, now)
    played = [m.move for m in _moves(session, game_id)]
    color = _color(game, resident_id)
    if (len(played) % 2 == 0) != (color == "white"):
        raise ChessDenied("NOT_YOUR_TURN", "wait for the other player")
    position, keys = rules.replay(played)
    try:
        move = rules.parse_move(position, text)
    except rules.ChessError as e:
        raise ChessDenied("BAD_MOVE", str(e)) from e
    after = rules.apply(position, move)
    session.add(
        ChessMove(
            game_id=game_id, ply=len(played) + 1, move=rules.move_text(move), by=color, at=now
        )
    )
    game.fen, game.draw_offer_by, game.updated_at = rules.to_fen(after), None, now
    end = rules.outcome(after, [*keys, rules._key(after)])
    if end.over:
        _finish(game, end.result, end.reason or "", now)
    session.flush()
    return game


def _rate_check(session: Session, resident_id: int, now: datetime) -> None:
    n = session.execute(
        select(func.count())
        .select_from(ChessMove)
        .join(ChessGame, ChessGame.id == ChessMove.game_id)
        .where(
            ChessMove.at > now - timedelta(minutes=1),
            or_(
                (ChessGame.resident_id == resident_id) & (ChessMove.by == "white"),
                (ChessGame.black_resident_id == resident_id) & (ChessMove.by == "black"),
            ),
        )
    ).scalar()
    if n >= settings(session)["moves_per_minute"]:
        raise ChessDenied("RATE_LIMITED", "slow down a little")


def draw(session: Session, resident_id: int, game_id: int, action: str, now: datetime) -> ChessGame:
    game = _mine(session, resident_id, game_id, lock=True)
    if game.status != "active":
        raise ChessDenied("NOT_ACTIVE", "this game is not active")
    color = _color(game, resident_id)
    if action == "offer":
        if game.draw_offer_by:
            raise ChessDenied("OFFER_OPEN", "a draw is already offered")
        game.draw_offer_by = color
    elif action in ("accept", "decline"):
        if not game.draw_offer_by or game.draw_offer_by == color:
            raise ChessDenied("NO_OFFER", "there is no draw offer to answer")
        if action == "accept":
            _finish(game, "draw", "agreed", now)
        else:
            game.draw_offer_by = None
    else:
        raise ChessDenied("BAD_ACTION", "offer, accept or decline")
    game.updated_at = now
    session.flush()
    return game


def leave(session: Session, resident_id: int, game_id: int, now: datetime) -> ChessGame:
    """Resigns an active match or cancels a waiting one. Always allowed, whatever the locks say,
    and it has no consequence beyond the result: no points, no sanction, no flag."""
    game = _mine(session, resident_id, game_id, lock=True)
    if game.status == "waiting":
        _finish(game, None, "cancelled", now)
    elif game.status == "active":
        winner = "black" if _color(game, resident_id) == "white" else "white"
        _finish(game, winner, "resigned", now)
    session.flush()
    return game


# ---------------- what the resident sees ----------------
def match_view(session: Session, resident_id: int, game_id: int) -> dict:
    """Only what a player may see: their colour, both handles, the moves and the position.
    Never the other resident's name, code, unit or line."""
    game = _mine(session, resident_id, game_id)
    color = _color(game, resident_id)
    moves = _moves(session, game_id)
    mine, theirs = (
        (game.white_handle, game.black_handle)
        if color == "white"
        else (game.black_handle, game.white_handle)
    )
    offer = None
    if game.draw_offer_by:
        offer = "you" if game.draw_offer_by == color else "them"
    return {
        "id": game.id,
        "opponent": "human",
        "status": game.status,
        "you": color,
        "your_handle": mine,
        "opponent_handle": theirs,
        "fen": game.fen or rules.START_FEN,
        "turn": "white" if len(moves) % 2 == 0 else "black",
        "moves": [{"ply": m.ply, "move": m.move} for m in moves],
        "result": game.result,
        "reason": game.result_reason,
        "draw_offer": offer,
        "wait_until": game.wait_until.isoformat() if game.wait_until else None,
    }


def history(session: Session, resident_id: int) -> list[dict]:
    """The resident's own games, newest first: just kind, level or handle, and how it ended."""
    rows = session.execute(
        select(ChessGame)
        .where(
            or_(ChessGame.resident_id == resident_id, ChessGame.black_resident_id == resident_id)
        )
        .order_by(ChessGame.id.desc())
        .limit(30)
    ).scalars()
    out = []
    for g in rows:
        if g.opponent_kind == "human":
            out.append(match_view(session, resident_id, g.id) | {"moves": []})
        else:
            out.append(
                {
                    "id": g.id,
                    "opponent": "engine",
                    "level": g.level,
                    "status": g.status,
                    "result": g.result,
                    "reason": g.result_reason,
                }
            )
    return out


# ---------------- staff ----------------
def match_log(session: Session, limit: int = 100, offset: int = 0) -> list[dict]:
    """The match log for staff: who played whom, handles, moves and result. Read-only."""
    white = Resident.__table__.alias("w")
    black = Resident.__table__.alias("b")
    rows = session.execute(
        select(ChessGame, white.c.code, black.c.code)
        .join(white, white.c.id == ChessGame.resident_id)
        .outerjoin(black, black.c.id == ChessGame.black_resident_id)
        .order_by(ChessGame.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    plies = dict(
        session.execute(select(ChessMove.game_id, func.count()).group_by(ChessMove.game_id)).all()
    )
    return [
        {
            "id": g.id,
            "opponent": g.opponent_kind,
            "level": g.level,
            "status": g.status,
            "white": w,
            "black": b,
            "white_handle": g.white_handle,
            "black_handle": g.black_handle,
            "result": g.result,
            "reason": g.result_reason,
            "plies": plies.get(g.id, 0),
            "started_at": g.created_at.isoformat(),
            "updated_at": g.updated_at.isoformat() if g.updated_at else None,
        }
        for g, w, b in rows
    ]
