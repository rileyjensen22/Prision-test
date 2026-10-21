"""Texting, video, chess, reading, jobs and rec-time endpoints for the kiosk (device token)."""

from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from isd.auth import DeviceContext, current_device
from isd.db import get_db
from isd.engine.calls import CallDenied
from isd.routers.device_features import _call_out
from isd.services import calls, chess, jobs, reading, rec, texting

router = APIRouter(prefix="/device", tags=["device-extras"])


def _now() -> datetime:
    return datetime.now(UTC)


def _err(e: Exception) -> HTTPException:
    code = getattr(e, "code", "ERROR")
    return HTTPException(404 if code == "NOT_FOUND" else 409, {"code": code, "message": str(e)})


# ---------------- texting ----------------
class TextIn(BaseModel):
    contact_id: int
    body: str = Field(max_length=2000)


@router.get("/messages")
def messages(
    contact_id: int, ctx: DeviceContext = Depends(current_device), db: Session = Depends(get_db)
):
    return [
        {
            "id": m.id,
            "direction": m.direction,
            "body": m.body,
            "private": m.privileged,
            "at": m.created_at.isoformat(),
        }
        for m in texting.thread(db, ctx.resident_id, contact_id)
    ]


@router.post("/messages", status_code=201)
def send_message(
    body: TextIn, ctx: DeviceContext = Depends(current_device), db: Session = Depends(get_db)
):
    try:
        m = texting.send_text(db, ctx.resident_id, body.contact_id, body.body, _now())
    except texting.TextDenied as e:
        raise _err(e) from e
    return {"id": m.id, "private": m.privileged, "monitored": m.monitored}


# ---------------- video ----------------
class VideoIn(BaseModel):
    contact_id: int


@router.post("/video-calls", status_code=201)
def start_video(
    body: VideoIn, ctx: DeviceContext = Depends(current_device), db: Session = Depends(get_db)
):
    try:
        return _call_out(
            calls.start_call(db, ctx.resident_id, body.contact_id, _now(), medium="video")
        )
    except CallDenied as e:
        raise _err(e) from e


@router.post("/video-calls/{call_id}/tamper")
def video_tamper(
    call_id: int, ctx: DeviceContext = Depends(current_device), db: Session = Depends(get_db)
):
    """Camera covered during a video call: ends the call; DEVICE_TAMPER goes to a supervisor."""
    try:
        s = calls.report_video_tamper(db, ctx.resident_id, call_id, _now())
    except CallDenied as e:
        raise _err(e) from e
    return {"sanction_id": s.id, "status": s.status}


# ---------------- chess ----------------
class GameIn(BaseModel):
    opponent: str


class MoveIn(BaseModel):
    move: str


def _game_out(db, g) -> dict:
    return {
        "id": g.id,
        "opponent": g.opponent_kind,
        "status": g.status,
        "moves": [{"ply": m.ply, "move": m.move, "by": m.by} for m in chess.moves(db, g.id)],
    }


@router.get("/chess")
def list_games(ctx: DeviceContext = Depends(current_device), db: Session = Depends(get_db)):
    from sqlalchemy import select

    from isd.models import ChessGame

    rows = db.execute(
        select(ChessGame).where(ChessGame.resident_id == ctx.resident_id).order_by(ChessGame.id)
    ).scalars()
    return [_game_out(db, g) for g in rows]


@router.post("/chess", status_code=201)
def new_game(
    body: GameIn, ctx: DeviceContext = Depends(current_device), db: Session = Depends(get_db)
):
    try:
        return _game_out(db, chess.new_game(db, ctx.resident_id, body.opponent, _now()))
    except chess.ChessDenied as e:
        raise _err(e) from e


@router.post("/chess/{game_id}/moves")
def play(
    game_id: int,
    body: MoveIn,
    ctx: DeviceContext = Depends(current_device),
    db: Session = Depends(get_db),
):
    try:
        chess.play(db, ctx.resident_id, game_id, body.move, _now())
    except chess.ChessDenied as e:
        raise _err(e) from e
    return _game_out(
        db, db.get(__import__("isd.models", fromlist=["ChessGame"]).ChessGame, game_id)
    )


# ---------------- reading ----------------
@router.get("/reading")
def reading_list(ctx: DeviceContext = Depends(current_device), db: Session = Depends(get_db)):
    return reading.list_items(db, ctx.resident_id, _now())


@router.get("/reading/{item_id}")
def reading_item(
    item_id: str, ctx: DeviceContext = Depends(current_device), db: Session = Depends(get_db)
):
    try:
        return reading.read_item(db, ctx.resident_id, item_id, _now())
    except reading.ReadingDenied as e:
        raise _err(e) from e


# ---------------- jobs (voluntary) ----------------
@router.get("/jobs")
def job_list(ctx: DeviceContext = Depends(current_device), db: Session = Depends(get_db)):
    return {"pay_split": jobs.pay_split(db), "jobs": jobs.list_listings(db, ctx.resident_id)}


@router.post("/jobs/{listing_id}/join", status_code=201)
def job_join(
    listing_id: int, ctx: DeviceContext = Depends(current_device), db: Session = Depends(get_db)
):
    try:
        jobs.opt_in(db, ctx.resident_id, listing_id, _now())
    except jobs.JobError as e:
        raise _err(e) from e
    return {"joined": True}


@router.post("/jobs/{listing_id}/leave")
def job_leave(
    listing_id: int, ctx: DeviceContext = Depends(current_device), db: Session = Depends(get_db)
):
    try:
        jobs.leave(db, ctx.resident_id, listing_id, _now())
    except jobs.JobError as e:
        raise _err(e) from e
    return {"joined": False}


# ---------------- rec time ----------------
class RecIn(BaseModel):
    day: date
    slot: str


@router.get("/rec")
def rec_day(
    day: date | None = None,
    ctx: DeviceContext = Depends(current_device),
    db: Session = Depends(get_db),
):
    now = _now()
    return rec.day_view(db, ctx.resident_id, day or now.date(), now)


@router.post("/rec/book", status_code=201)
def rec_book(
    body: RecIn, ctx: DeviceContext = Depends(current_device), db: Session = Depends(get_db)
):
    try:
        rec.book(db, ctx.resident_id, body.day, body.slot, _now())
    except rec.RecDenied as e:
        raise _err(e) from e
    return {"booked": True}


@router.post("/rec/cancel")
def rec_cancel(
    body: RecIn, ctx: DeviceContext = Depends(current_device), db: Session = Depends(get_db)
):
    return {"cancelled": rec.cancel(db, ctx.resident_id, body.day, body.slot)}
