"""Chess rules for server-side move checking in human matches. Pure functions, no database.

Written for this project (MIT, like the rest of the repo) because the usual Python library is GPL.
Squares are 0..63 with a1 = 0, b1 = 1, ... h8 = 63. A move is "e2e4" (plus q/r/b/n when promoting).
Correctness is checked against known perft counts in tests/engine/test_chess_rules.py.
"""

from dataclasses import dataclass

START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
FILES = "abcdefgh"
KNIGHT = ((1, 2), (2, 1), (2, -1), (1, -2), (-1, -2), (-2, -1), (-2, 1), (-1, 2))
KING = ((1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1))
BISHOP = ((1, 1), (-1, 1), (-1, -1), (1, -1))
ROOK = ((1, 0), (0, 1), (-1, 0), (0, -1))


class ChessError(ValueError):
    pass


@dataclass(frozen=True)
class Position:
    board: tuple[str, ...]  # 64 entries, "" for empty, uppercase = white
    white_to_move: bool
    castling: str  # subset of "KQkq", or ""
    ep: int | None  # square a pawn just passed over, if a capture there is possible
    halfmove: int
    fullmove: int


def sq_name(sq: int) -> str:
    return f"{FILES[sq % 8]}{sq // 8 + 1}"


def sq_index(name: str) -> int:
    if len(name) != 2 or name[0] not in FILES or name[1] not in "12345678":
        raise ChessError("bad square")
    return int(name[1]) - 1 << 3 | FILES.index(name[0])


def from_fen(fen: str) -> Position:
    parts = fen.split()
    if len(parts) != 6:
        raise ChessError("bad FEN")
    board: list[str] = []
    for row in reversed(parts[0].split("/")):
        for ch in row:
            board.extend([""] * int(ch) if ch.isdigit() else [ch])
    if len(board) != 64:
        raise ChessError("bad FEN")
    return Position(
        tuple(board),
        parts[1] == "w",
        "" if parts[2] == "-" else parts[2],
        None if parts[3] == "-" else sq_index(parts[3]),
        int(parts[4]),
        int(parts[5]),
    )


def to_fen(p: Position) -> str:
    rows = []
    for rank in range(7, -1, -1):
        row, empty = "", 0
        for f in range(8):
            piece = p.board[rank * 8 + f]
            if piece:
                row += (str(empty) if empty else "") + piece
                empty = 0
            else:
                empty += 1
        rows.append(row + (str(empty) if empty else ""))
    return " ".join(
        [
            "/".join(rows),
            "w" if p.white_to_move else "b",
            p.castling or "-",
            sq_name(p.ep) if p.ep is not None else "-",
            str(p.halfmove),
            str(p.fullmove),
        ]
    )


def _own(piece: str, white: bool) -> bool:
    return bool(piece) and piece.isupper() == white


def attacked(board: tuple[str, ...], sq: int, by_white: bool) -> bool:
    """Is `sq` attacked by the given colour?"""
    f, r = sq % 8, sq // 8

    def at(df: int, dr: int) -> str:
        nf, nr = f + df, r + dr
        return board[nr * 8 + nf] if 0 <= nf < 8 and 0 <= nr < 8 else ""

    pawn_dr = -1 if by_white else 1  # the pawn sits one rank behind the square it attacks
    for df in (-1, 1):
        if at(df, pawn_dr) == ("P" if by_white else "p"):
            return True
    knight, king = ("N", "K") if by_white else ("n", "k")
    if any(at(df, dr) == knight for df, dr in KNIGHT):
        return True
    if any(at(df, dr) == king for df, dr in KING):
        return True
    for dirs, kinds in ((BISHOP, "BQ"), (ROOK, "RQ")):
        kinds = kinds if by_white else kinds.lower()
        for df, dr in dirs:
            k = 1
            while True:
                piece = at(df * k, dr * k)
                nf, nr = f + df * k, r + dr * k
                if not (0 <= nf < 8 and 0 <= nr < 8):
                    break
                if piece:
                    if piece in kinds:
                        return True
                    break
                k += 1
    return False


def _king_square(board: tuple[str, ...], white: bool) -> int:
    return board.index("K" if white else "k")


def in_check(p: Position) -> bool:
    return attacked(p.board, _king_square(p.board, p.white_to_move), not p.white_to_move)


def _pseudo(p: Position) -> list[tuple[int, int, str]]:
    out: list[tuple[int, int, str]] = []
    white = p.white_to_move
    b = p.board
    for sq, piece in enumerate(b):
        if not _own(piece, white):
            continue
        f, r = sq % 8, sq // 8
        kind = piece.upper()
        if kind == "P":
            step = 1 if white else -1
            start, last = (1, 7) if white else (6, 0)
            ahead = sq + 8 * step
            targets = []
            if 0 <= ahead < 64 and not b[ahead]:
                targets.append(ahead)
                if r == start and not b[ahead + 8 * step]:
                    targets.append(ahead + 8 * step)
            for df in (-1, 1):
                if 0 <= f + df < 8 and 0 <= r + step < 8:
                    t = sq + 8 * step + df
                    if (b[t] and not _own(b[t], white)) or t == p.ep:
                        targets.append(t)
            for t in targets:
                if t // 8 == last:
                    out.extend((sq, t, promo) for promo in "qrbn")
                else:
                    out.append((sq, t, ""))
        elif kind in "NK":
            for df, dr in KNIGHT if kind == "N" else KING:
                nf, nr = f + df, r + dr
                if 0 <= nf < 8 and 0 <= nr < 8 and not _own(b[nr * 8 + nf], white):
                    out.append((sq, nr * 8 + nf, ""))
        else:
            dirs = BISHOP if kind == "B" else ROOK if kind == "R" else BISHOP + ROOK
            for df, dr in dirs:
                nf, nr = f + df, r + dr
                while 0 <= nf < 8 and 0 <= nr < 8:
                    target = b[nr * 8 + nf]
                    if _own(target, white):
                        break
                    out.append((sq, nr * 8 + nf, ""))
                    if target:
                        break
                    nf, nr = nf + df, nr + dr
    out.extend(_castles(p))
    return out


def _castles(p: Position) -> list[tuple[int, int, str]]:
    white = p.white_to_move
    home = 0 if white else 56
    king = "K" if white else "k"
    if p.board[home + 4] != king or in_check(p):
        return []
    out = []
    side_k, side_q = ("K", "Q") if white else ("k", "q")
    rook = "R" if white else "r"
    if side_k in p.castling and p.board[home + 7] == rook:
        free = not p.board[home + 5] and not p.board[home + 6]
        safe = not any(attacked(p.board, home + s, not white) for s in (5, 6))
        if free and safe:
            out.append((home + 4, home + 6, ""))
    if side_q in p.castling and p.board[home] == rook:
        free = not any(p.board[home + s] for s in (1, 2, 3))
        safe = not any(attacked(p.board, home + s, not white) for s in (2, 3))
        if free and safe:
            out.append((home + 4, home + 2, ""))
    return out


def apply(p: Position, move: tuple[int, int, str]) -> Position:
    """The position after a move that is assumed pseudo-legal."""
    src, dst, promo = move
    b = list(p.board)
    piece = b[src]
    white = p.white_to_move
    captured = b[dst]
    b[dst], b[src] = piece, ""
    kind = piece.upper()
    if kind == "P" and dst == p.ep:
        b[dst + (-8 if white else 8)] = ""
        captured = "p"
    if kind == "K" and abs(dst - src) == 2:
        row = src - src % 8
        if dst > src:
            b[row + 5], b[row + 7] = b[row + 7], ""
        else:
            b[row + 3], b[row] = b[row], ""
    if promo:
        b[dst] = promo.upper() if white else promo
    rights = p.castling
    for square, right in ((0, "Q"), (7, "K"), (56, "q"), (63, "k")):
        if src == square or dst == square:
            rights = rights.replace(right, "")
    if kind == "K":
        rights = (
            rights.replace("K", "").replace("Q", "")
            if white
            else (rights.replace("k", "").replace("q", ""))
        )
    ep = (src + dst) // 2 if kind == "P" and abs(dst - src) == 16 else None
    return Position(
        tuple(b),
        not white,
        rights,
        ep,
        0 if kind == "P" or captured else p.halfmove + 1,
        p.fullmove + (0 if white else 1),
    )


def legal_moves(p: Position) -> list[tuple[int, int, str]]:
    white = p.white_to_move
    out = []
    for m in _pseudo(p):
        after = apply(p, m)
        if not attacked(after.board, _king_square(after.board, white), not white):
            out.append(m)
    return out


def move_text(m: tuple[int, int, str]) -> str:
    return f"{sq_name(m[0])}{sq_name(m[1])}{m[2]}"


def parse_move(p: Position, text: str) -> tuple[int, int, str]:
    """The legal move written as `text` (e2e4, e7e8q) or ChessError."""
    if len(text) not in (4, 5):
        raise ChessError("write the move like e2e4")
    try:
        want = (sq_index(text[:2]), sq_index(text[2:4]), text[4:].lower())
    except ChessError as e:
        raise ChessError("write the move like e2e4") from e
    if want[2] and want[2] not in "qrbn":
        raise ChessError("write the move like e2e4")
    for m in legal_moves(p):
        if m == want:
            return m
    raise ChessError("that move is not allowed")


def perft(p: Position, depth: int) -> int:
    if depth == 0:
        return 1
    return sum(perft(apply(p, m), depth - 1) for m in legal_moves(p))


def _insufficient(p: Position) -> bool:
    pieces = [x for x in p.board if x and x.upper() != "K"]
    if not pieces:
        return True
    if len(pieces) == 1 and pieces[0].upper() in "BN":
        return True
    if all(x.upper() == "B" for x in pieces):  # bishops all on one colour
        colours = {(i // 8 + i % 8) % 2 for i, x in enumerate(p.board) if x and x.upper() == "B"}
        return len(colours) == 1
    return False


def _key(p: Position) -> str:
    return " ".join(to_fen(p).split()[:4])


@dataclass(frozen=True)
class Outcome:
    over: bool
    result: str | None = None  # white | black | draw
    reason: str | None = None  # checkmate | stalemate | insufficient | repetition | seventy_five


def outcome(p: Position, seen: list[str] | None = None) -> Outcome:
    """`seen` are the position keys so far, including this one (see `_key`)."""
    if not legal_moves(p):
        if in_check(p):
            return Outcome(True, "black" if p.white_to_move else "white", "checkmate")
        return Outcome(True, "draw", "stalemate")
    if _insufficient(p):
        return Outcome(True, "draw", "insufficient")
    if p.halfmove >= 150:
        return Outcome(True, "draw", "seventy_five")
    if seen and seen.count(_key(p)) >= 3:
        return Outcome(True, "draw", "repetition")
    return Outcome(False)


def replay(moves: list[str]) -> tuple[Position, list[str]]:
    """The position after a list of moves from the start, and every position key along the way."""
    p = from_fen(START_FEN)
    keys = [_key(p)]
    for text in moves:
        p = apply(p, parse_move(p, text))
        keys.append(_key(p))
    return p, keys
