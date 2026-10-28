"""The server-side chess rules, checked against well-known perft counts (all legal move paths to
a depth): they only match if castling, en passant, promotion, pins and checks are all right."""

import pytest

from isd.engine import chess_rules as c

KIWIPETE = "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1"
POSITION_3 = "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1"
POSITION_4 = "r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1"
POSITION_5 = "rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8"


@pytest.mark.parametrize(
    ("fen", "depth", "nodes"),
    [
        (c.START_FEN, 1, 20),
        (c.START_FEN, 3, 8902),
        (KIWIPETE, 1, 48),
        (KIWIPETE, 2, 2039),
        (KIWIPETE, 3, 97862),
        (POSITION_3, 3, 2812),
        (POSITION_4, 3, 9467),
        (POSITION_5, 2, 1486),
    ],
)
def test_perft_matches_the_published_counts(fen, depth, nodes):
    assert c.perft(c.from_fen(fen), depth) == nodes


def test_fen_round_trips():
    for fen in (c.START_FEN, KIWIPETE, POSITION_3):
        assert c.to_fen(c.from_fen(fen)) == fen


def test_fools_mate_is_checkmate_and_black_wins():
    p, keys = c.replay(["f2f3", "e7e5", "g2g4", "d8h4"])
    out = c.outcome(p, keys)
    assert out.over and out.result == "black" and out.reason == "checkmate"


def test_illegal_and_malformed_moves_are_refused():
    p = c.from_fen(c.START_FEN)
    for bad in ("e2e5", "e7e5", "zz", "e2e4q", "e2", "", "e2e4e4", "a1a2"):
        with pytest.raises(c.ChessError):
            c.parse_move(p, bad)


def test_stalemate_and_insufficient_material_are_draws():
    stale = c.from_fen("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1")
    assert c.outcome(stale).reason == "stalemate"
    bare = c.from_fen("8/8/8/4k3/8/3K4/8/6N1 w - - 0 1")
    assert c.outcome(bare).reason == "insufficient"


def test_threefold_repetition_is_a_draw():
    shuffle = ["g1f3", "g8f6", "f3g1", "f6g8"] * 2
    p, keys = c.replay(shuffle)
    assert c.outcome(p, keys).reason == "repetition"


def test_promotion_needs_a_piece_letter_and_en_passant_works():
    p = c.from_fen("8/P7/8/8/8/8/k6K/8 w - - 0 1")
    assert {c.move_text(m) for m in c.legal_moves(p) if m[0] == 48} == {
        "a7a8q",
        "a7a8r",
        "a7a8b",
        "a7a8n",
    }
    ep = c.from_fen("rnbqkbnr/ppp1pppp/8/8/3pP3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 3")
    assert "d4e3" in {c.move_text(m) for m in c.legal_moves(ep)}
