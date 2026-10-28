"""Chess (invariant 13): engine games are logged, human matches are paired by the server under
strict rules, moves are checked, and nothing a resident can send is free text."""

from datetime import timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from isd.main import app
from isd.models import (
    Cell,
    ChessGame,
    ChessMove,
    Device,
    DeviceAssignment,
    KeepSeparate,
    PointEvent,
    Resident,
    Sanction,
)
from isd.services import chess, points
from isd.services.audit import SYSTEM
from isd.services.config_store import get_current, set_config
from tests.conftest import NOW

FOOLS_MATE = ["f2f3", "e7e5", "g2g4", "d8h4"]


@pytest.fixture
def place(owner):
    """Gives a resident a cell on a line and unit, and tier-5 points so human chess is open."""
    counter = iter(range(10_000))

    def _place(rid, line="L1", unit="A", points_needed=700):
        n = next(counter)
        cell = Cell(code=f"CH-{rid}-{n}", unit=unit, line_code=line)
        dev = Device(code=f"CHD-{rid}-{n}")
        owner.add_all([cell, dev])
        owner.flush()
        owner.add(
            DeviceAssignment(
                device_id=dev.id,
                cell_id=cell.id,
                resident_id=rid,
                assigned_at=NOW - timedelta(days=2),
            )
        )
        if points_needed:
            points.record_points(
                owner,
                SYSTEM,
                rid,
                "seed_adjustment",
                points_needed,
                "system",
                NOW - timedelta(days=1),
            )
            points.evaluate_tier(owner, rid, NOW)
        owner.flush()
        return rid

    return _place


@pytest.fixture
def pair(owner, seeded, make_resident, place):
    """Two tier-5 residents on different lines."""
    return place(make_resident(), "L1"), place(make_resident(), "L2")


def start(owner, a, b, now=NOW):
    first = chess.find_match(owner, a, now)
    second = chess.find_match(owner, b, now)
    assert second.id == first.id and second.status == "active"
    return second


# ---------------- engine games ----------------
def test_engine_games_are_logged_and_levels_come_from_config(owner, seeded, make_resident, place):
    rid = place(make_resident(), points_needed=100)  # tier 2: engine, not human
    assert [lv["level"] for lv in chess.levels(owner)] == [1, 2, 3, 4, 5]
    with pytest.raises(chess.ChessDenied) as e:
        chess.new_engine_game(owner, rid, 9, NOW)
    assert e.value.code == "BAD_LEVEL"
    g = chess.new_engine_game(owner, rid, 3, NOW)
    chess.finish_engine_game(owner, rid, g.id, "white", "checkmate", NOW)
    assert (g.status, g.result, g.level) == ("finished", "white", 3)
    with pytest.raises(chess.ChessDenied) as e:
        chess.find_match(owner, rid, NOW)
    assert e.value.code == "FEATURE_LOCKED"  # tier 2 has no human play


def test_a_tier_one_resident_has_no_chess(owner, seeded, make_resident, place):
    rid = place(make_resident(), points_needed=0)
    with pytest.raises(chess.ChessDenied):
        chess.new_engine_game(owner, rid, 1, NOW)


# ---------------- pairing rules ----------------
def test_two_residents_on_different_lines_are_paired_with_random_handles(owner, pair):
    a, b = pair
    waiting = chess.find_match(owner, a, NOW)
    assert waiting.status == "waiting"
    assert chess.find_match(owner, a, NOW).id == waiting.id  # asking again reuses the open match
    g = chess.find_match(owner, b, NOW)
    assert g.id == waiting.id and g.status == "active"
    va, vb = chess.match_view(owner, a, g.id), chess.match_view(owner, b, g.id)
    assert (va["you"], vb["you"]) == ("white", "black")
    assert va["your_handle"] == vb["opponent_handle"] and vb["your_handle"] == va["opponent_handle"]
    assert va["your_handle"] != va["opponent_handle"]
    codes = {r.code for r in owner.execute(select(Resident)).scalars()}
    assert not any(c in repr([va, vb]) for c in codes)


def test_residents_on_the_same_line_are_never_paired(owner, seeded, make_resident, place):
    a, b = place(make_resident(), "L1"), place(make_resident(), "L1", unit="B")
    chess.find_match(owner, a, NOW)
    g = chess.find_match(owner, b, NOW)
    assert g.status == "waiting" and g.resident_id == b  # b waits too; nobody was matched
    assert (
        owner.execute(select(ChessGame).where(ChessGame.black_resident_id.isnot(None))).first()
        is None
    )


def test_a_resident_with_no_line_is_never_paired(owner, seeded, make_resident, place):
    a, b = place(make_resident(), None), place(make_resident(), "L2")
    chess.find_match(owner, a, NOW)
    assert chess.find_match(owner, b, NOW).status == "waiting"


@pytest.mark.parametrize("swap", [False, True])
def test_keep_separate_pairs_are_never_matched(owner, pair, swap):
    a, b = pair
    lo, hi = sorted((a, b))
    owner.add(KeepSeparate(resident_a_id=lo, resident_b_id=hi, reason="test", added_at=NOW))
    owner.flush()
    first, second = (b, a) if swap else (a, b)
    chess.find_match(owner, first, NOW)
    assert chess.find_match(owner, second, NOW).status == "waiting"


def test_an_ended_keep_separate_record_no_longer_blocks(owner, pair):
    a, b = pair
    lo, hi = sorted((a, b))
    owner.add(
        KeepSeparate(resident_a_id=lo, resident_b_id=hi, reason="test", added_at=NOW, ended_at=NOW)
    )
    owner.flush()
    start(owner, a, b)


# ---------------- who may play humans ----------------
def test_a_games_sanction_blocks_human_play_but_not_the_engine(owner, pair):
    a, _ = pair
    owner.add(
        Sanction(
            resident_id=a,
            infraction_code="DISRUPT",
            scope="games",
            reason_code="DISRUPT",
            status="active",
            starts_at=NOW - timedelta(hours=1),
            ends_at=NOW + timedelta(hours=23),
        )
    )
    owner.flush()
    with pytest.raises(chess.ChessDenied) as e:
        chess.find_match(owner, a, NOW)
    assert e.value.code == "FEATURE_LOCKED"
    assert chess.new_engine_game(owner, a, 1, NOW).status == "active"


def test_staff_can_switch_human_chess_off_per_resident_and_per_unit_and_facility(
    owner, seeded, make_resident, place
):
    a, b, c = (place(make_resident(), "L1", unit="A"), place(make_resident(), "L2", unit="B"), None)
    owner.get(Resident, a).chess_human = False
    owner.flush()
    with pytest.raises(chess.ChessDenied):
        chess.find_match(owner, a, NOW)
    assert chess.new_engine_game(owner, a, 1, NOW)  # the engine is not affected
    owner.get(Resident, a).chess_human = None
    cfg = dict(get_current(owner, "chess").payload, disabled_units=["B"])
    set_config(owner, SYSTEM, "chess", cfg, "test: unit B off")
    assert chess.find_match(owner, a, NOW).status == "waiting"
    with pytest.raises(chess.ChessDenied):
        chess.find_match(owner, b, NOW)
    owner.get(Resident, b).chess_human = True  # a named resident stays on when only the unit is off
    assert chess.find_match(owner, b, NOW).status == "active"
    set_config(owner, SYSTEM, "chess", dict(cfg, human_enabled=False), "test: facility off")
    with pytest.raises(chess.ChessDenied):
        chess.find_match(owner, make_resident(), NOW)
    assert c is None


# ---------------- playing ----------------
def test_moves_are_checked_and_turns_alternate(owner, pair):
    a, b = pair
    g = start(owner, a, b)
    with pytest.raises(chess.ChessDenied) as e:
        chess.play_move(owner, b, g.id, "e7e5", NOW)
    assert e.value.code == "NOT_YOUR_TURN"
    for bad in ("e2e5", "a1a2", "e2e4q"):
        with pytest.raises(chess.ChessDenied) as e:
            chess.play_move(owner, a, g.id, bad, NOW)
        assert e.value.code == "BAD_MOVE"
    chess.play_move(owner, a, g.id, "e2e4", NOW)
    chess.play_move(owner, b, g.id, "e7e5", NOW)
    view = chess.match_view(owner, a, g.id)
    assert [m["move"] for m in view["moves"]] == ["e2e4", "e7e5"] and view["turn"] == "white"


def test_a_checkmate_ends_the_match_and_no_more_moves_are_taken(owner, pair):
    a, b = pair
    g = start(owner, a, b)
    for i, mv in enumerate(FOOLS_MATE):
        chess.play_move(owner, a if i % 2 == 0 else b, g.id, mv, NOW)
    view = chess.match_view(owner, a, g.id)
    assert (view["status"], view["result"], view["reason"]) == ("finished", "black", "checkmate")
    with pytest.raises(chess.ChessDenied) as e:
        chess.play_move(owner, a, g.id, "e2e4", NOW)
    assert e.value.code == "NOT_ACTIVE"


def test_draw_offers_can_be_accepted_declined_and_a_move_declines_them(owner, pair):
    a, b = pair
    g = start(owner, a, b)
    chess.draw(owner, a, g.id, "offer", NOW)
    assert chess.match_view(owner, b, g.id)["draw_offer"] == "them"
    with pytest.raises(chess.ChessDenied) as e:
        chess.draw(owner, a, g.id, "accept", NOW)  # you cannot accept your own offer
    assert e.value.code == "NO_OFFER"
    chess.draw(owner, b, g.id, "decline", NOW)
    chess.draw(owner, a, g.id, "offer", NOW)
    chess.play_move(owner, a, g.id, "e2e4", NOW)  # moving ignores the offer
    assert chess.match_view(owner, b, g.id)["draw_offer"] is None
    chess.draw(owner, b, g.id, "offer", NOW)
    chess.draw(owner, a, g.id, "accept", NOW)
    view = chess.match_view(owner, a, g.id)
    assert (view["result"], view["reason"]) == ("draw", "agreed")


def test_leaving_has_no_penalty_and_works_even_when_locked(owner, pair):
    a, b = pair
    g = start(owner, a, b)
    before = (
        owner.execute(select(PointEvent)).scalars().all().__len__(),
        owner.execute(select(Sanction)).scalars().all().__len__(),
    )
    owner.add(
        Sanction(
            resident_id=a,
            infraction_code="DISRUPT",
            scope="all_non_baseline",
            reason_code="DISRUPT",
            status="active",
            starts_at=NOW - timedelta(hours=1),
            ends_at=NOW + timedelta(hours=23),
        )
    )
    owner.flush()
    with pytest.raises(chess.ChessDenied):
        chess.play_move(owner, a, g.id, "e2e4", NOW)  # a sanction takes effect mid-match
    chess.leave(owner, a, g.id, NOW)
    view = chess.match_view(owner, b, g.id)
    assert (view["result"], view["reason"]) == ("black", "resigned")
    after = (
        owner.execute(select(PointEvent)).scalars().all().__len__(),
        owner.execute(select(Sanction)).scalars().all().__len__(),
    )
    assert after == (before[0], before[1] + 1)  # only the sanction this test added


def test_a_waiting_match_can_be_cancelled_and_expires(owner, pair):
    a, b = pair
    g = chess.find_match(owner, a, NOW)
    chess.leave(owner, a, g.id, NOW)
    assert chess.match_view(owner, a, g.id)["reason"] == "cancelled"
    waiting = chess.find_match(owner, a, NOW)
    later = NOW + timedelta(minutes=chess.settings(owner)["queue_minutes"] + 1)
    fresh = chess.find_match(owner, b, later)
    assert fresh.id != waiting.id and fresh.status == "waiting"
    assert owner.get(ChessGame, waiting.id).result_reason == "expired"


def test_only_the_two_players_can_see_or_touch_a_match(owner, pair, make_resident, place):
    a, b = pair
    g = start(owner, a, b)
    outsider = place(make_resident(), "L3")
    for call in (
        lambda: chess.match_view(owner, outsider, g.id),
        lambda: chess.play_move(owner, outsider, g.id, "e2e4", NOW),
        lambda: chess.draw(owner, outsider, g.id, "offer", NOW),
        lambda: chess.leave(owner, outsider, g.id, NOW),
    ):
        with pytest.raises(chess.ChessDenied) as e:
            call()
        assert e.value.code == "NOT_FOUND"


def test_moves_are_rate_limited(owner, pair):
    a, b = pair
    cfg = dict(get_current(owner, "chess").payload, moves_per_minute=2)
    set_config(owner, SYSTEM, "chess", cfg, "test: tight limit")
    g = start(owner, a, b)
    chess.play_move(owner, a, g.id, "e2e4", NOW)
    chess.play_move(owner, b, g.id, "e7e5", NOW)
    chess.play_move(owner, a, g.id, "g1f3", NOW)
    with pytest.raises(chess.ChessDenied) as e:
        chess.play_move(owner, a, g.id, "f1c4", NOW)
        chess.play_move(owner, b, g.id, "g8f6", NOW)
        chess.play_move(owner, a, g.id, "d2d3", NOW)
    assert e.value.code == "RATE_LIMITED"


# ---------------- no free text, no spectators, no stakes ----------------
def test_the_match_api_has_no_free_text_field():
    spec = app.openapi()
    schemas = spec["components"]["schemas"]
    for path, ops in spec["paths"].items():
        if not path.startswith("/device/chess"):
            continue
        for op in ops.values():
            body = op.get("requestBody")
            if not body:
                continue
            ref = body["content"]["application/json"]["schema"]["$ref"].split("/")[-1]
            for name, prop in schemas[ref]["properties"].items():
                is_text = prop.get("type") == "string" or "anyOf" in prop
                fixed = "enum" in prop or "pattern" in prop or "const" in prop
                assert not is_text or fixed, f"{path}.{name} accepts free text"
            assert schemas[ref].get("additionalProperties") is False


def test_extra_fields_are_refused_over_http(client, kiosk):
    rid, token, _ = kiosk()
    head = {"X-Device-Token": token}
    r = client.post("/device/chess", json={"opponent": "human", "note": "hello"}, headers=head)
    assert r.status_code == 422
    r = client.post("/device/chess/1/moves", json={"move": "e2e4", "chat": "hi"}, headers=head)
    assert r.status_code == 422


def test_there_is_no_spectator_route_and_no_stake_column():
    paths = [p for p in app.openapi()["paths"] if "chess" in p]
    assert not [p for p in paths if "watch" in p or "spectat" in p or "list" in p]
    cols = {c.name for t in (ChessGame, ChessMove) for c in t.__table__.columns}
    assert not [
        c for c in cols if any(w in c for w in ("stake", "wager", "bet", "item", "price", "chat"))
    ]


def test_the_match_view_never_names_the_other_resident(owner, pair):
    a, b = pair
    g = start(owner, a, b)
    view = chess.match_view(owner, a, g.id)
    assert set(view) == {
        "id", "opponent", "status", "you", "your_handle", "opponent_handle", "fen", "turn",
        "moves", "result", "reason", "draw_offer", "wait_until",
    }  # fmt: skip


# ---------------- the log ----------------
def test_the_match_log_is_for_staff_and_moves_cannot_be_rewritten(owner, pair):
    a, b = pair
    g = start(owner, a, b)
    chess.play_move(owner, a, g.id, "e2e4", NOW)
    log = chess.match_log(owner)
    row = next(r for r in log if r["id"] == g.id)
    assert row["white"] and row["black"] and row["plies"] == 1 and row["white_handle"]
    with pytest.raises(DBAPIError):
        owner.execute(text("UPDATE chess_moves SET move = 'a2a3'"))


def test_staff_routes_are_role_gated(client, staff_tokens):
    assert client.get("/staff/chess/matches", headers=staff_tokens["officer"]).status_code == 403
    assert client.get("/staff/chess/matches", headers=staff_tokens["supervisor"]).status_code == 200
    assert client.get("/staff/chess/matches", headers=staff_tokens["auditor"]).status_code == 200
    body = {"human": False, "reason": "testing the switch"}
    assert (
        client.put(
            "/staff/residents/1/chess", json=body, headers=staff_tokens["auditor"]
        ).status_code
        == 403
    )
