"""Texting, video, chess, reading, jobs and rec-time endpoints for the kiosk (device token)."""

from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from isd.auth import DeviceContext, current_device
from isd.db import get_db
from isd.engine.calls import CallDenied
from isd.routers.device_features import _call_out
from isd.services import (
    calls,
    chess,
    earnings,
    job_policy,
    jobs,
    reading,
    rec,
    reentry,
    texting,
    video_bookings,
    work_tasks,
)

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
            "delivery": m.delivery,
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
    return {"id": m.id, "private": m.privileged, "monitored": m.monitored, "delivery": m.delivery}


# ---------------- video ----------------
class VideoIn(BaseModel):
    contact_id: int


def _video_out(c) -> dict:
    out = _call_out(c)
    out["medium"] = c.medium
    out["connection"] = getattr(c, "connection", {})
    return out


@router.post("/video-calls", status_code=201)
def start_video(
    body: VideoIn, ctx: DeviceContext = Depends(current_device), db: Session = Depends(get_db)
):
    try:
        return _video_out(
            calls.start_call(db, ctx.resident_id, body.contact_id, _now(), medium="video")
        )
    except CallDenied as e:
        raise _err(e) from e


class TamperIn(BaseModel):
    """What the device may say about its camera: a derived signal and how long, never an image."""

    model_config = ConfigDict(extra="forbid")
    signal: str = Field(max_length=8)
    covered_ms: int = Field(ge=0, le=600_000)


@router.post("/video-calls/{call_id}/tamper")
def video_tamper(
    call_id: int,
    body: TamperIn,
    ctx: DeviceContext = Depends(current_device),
    db: Session = Depends(get_db),
):
    """Camera covered during a video call: ends the call; DEVICE_TAMPER goes to a supervisor."""
    try:
        s = calls.report_video_tamper(db, ctx.resident_id, call_id, _now(), body.signal)
    except CallDenied as e:
        raise _err(e) from e
    return {"sanction_id": s.id, "status": s.status}


class BookingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contact_id: int
    starts_at: datetime
    minutes: int = Field(ge=1, le=240)


def _booking_out(b) -> dict:
    return {
        "id": b.id,
        "contact_id": b.contact_id,
        "starts_at": b.starts_at.isoformat(),
        "minutes": b.minutes,
        "status": b.status,
    }


@router.get("/video-bookings")
def list_bookings(ctx: DeviceContext = Depends(current_device), db: Session = Depends(get_db)):
    return [_booking_out(b) for b in video_bookings.upcoming(db, ctx.resident_id, _now())]


@router.post("/video-bookings", status_code=201)
def book_video(
    body: BookingIn, ctx: DeviceContext = Depends(current_device), db: Session = Depends(get_db)
):
    try:
        b = video_bookings.book(
            db, ctx.resident_id, body.contact_id, body.starts_at, body.minutes, _now()
        )
    except CallDenied as e:
        raise _err(e) from e
    return _booking_out(b)


@router.post("/video-bookings/{booking_id}/cancel")
def cancel_booking(
    booking_id: int, ctx: DeviceContext = Depends(current_device), db: Session = Depends(get_db)
):
    try:
        return _booking_out(video_bookings.cancel(db, ctx.resident_id, booking_id, _now()))
    except CallDenied as e:
        raise _err(e) from e


@router.post("/video-bookings/{booking_id}/start", status_code=201)
def start_booking(
    booking_id: int, ctx: DeviceContext = Depends(current_device), db: Session = Depends(get_db)
):
    try:
        return _video_out(video_bookings.start_booked(db, ctx.resident_id, booking_id, _now()))
    except CallDenied as e:
        raise _err(e) from e


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


class ProgressIn(BaseModel):
    page: int = Field(ge=0, le=100_000)


class BookmarkIn(BaseModel):
    on: bool


@router.put("/reading/{item_id}/progress")
def reading_progress(
    item_id: str,
    body: ProgressIn,
    ctx: DeviceContext = Depends(current_device),
    db: Session = Depends(get_db),
):
    try:
        return reading.save_progress(db, ctx.resident_id, item_id, body.page, _now())
    except reading.ReadingDenied as e:
        raise _err(e) from e


@router.put("/reading/{item_id}/bookmarks/{page}")
def reading_bookmark(
    item_id: str,
    page: int,
    body: BookmarkIn,
    ctx: DeviceContext = Depends(current_device),
    db: Session = Depends(get_db),
):
    try:
        return reading.set_bookmark(db, ctx.resident_id, item_id, page, body.on, _now())
    except reading.ReadingDenied as e:
        raise _err(e) from e


# ---------------- jobs (voluntary) ----------------
@router.get("/jobs")
def job_list(ctx: DeviceContext = Depends(current_device), db: Session = Depends(get_db)):
    return {
        "pay_split": jobs.pay_split(db),
        "jobs": jobs.list_listings(db, ctx.resident_id),
        "earnings": earnings.summary(db, ctx.resident_id),
        "suspended": job_policy.suspension(db, ctx.resident_id, _now()),
    }


@router.get("/jobs/work-log")
def job_work_log(ctx: DeviceContext = Depends(current_device), db: Session = Depends(get_db)):
    return work_tasks.work_log(db, ctx.resident_id)


@router.get("/jobs/{listing_id}/task")
def job_next_task(
    listing_id: int, ctx: DeviceContext = Depends(current_device), db: Session = Depends(get_db)
):
    try:
        return work_tasks.next_task(db, ctx.resident_id, listing_id, _now())
    except jobs.JobError as e:
        if e.code == "JOB_SUSPENDED":  # a lock: reason, end time and how to appeal (invariant 5)
            raise HTTPException(
                409,
                {
                    "code": e.code,
                    "message": str(e),
                    "lock": job_policy.suspension(db, ctx.resident_id, _now()),
                },
            ) from e
        raise _err(e) from e


class TaskAnswerIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answer: str = Field(min_length=1, max_length=2000)


@router.post("/jobs/tasks/{task_id}/submit")
def job_submit_task(
    task_id: int,
    body: TaskAnswerIn,
    ctx: DeviceContext = Depends(current_device),
    db: Session = Depends(get_db),
):
    try:
        return work_tasks.submit(db, ctx.resident_id, task_id, body.answer, _now())
    except jobs.JobError as e:
        raise _err(e) from e


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
    block_id: int | None = None


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
        rec.book(db, ctx.resident_id, body.day, body.slot, _now(), body.block_id)
    except rec.RecDenied as e:
        raise _err(e) from e
    return {"booked": True}


@router.post("/rec/cancel")
def rec_cancel(
    body: RecIn, ctx: DeviceContext = Depends(current_device), db: Session = Depends(get_db)
):
    return {"cancelled": rec.cancel(db, ctx.resident_id, body.day, body.slot, body.block_id)}


# ---------------- reentry (information only, so not an entitlement feature) ----------------
@router.get("/reentry")
def reentry_view(ctx: DeviceContext = Depends(current_device), db: Session = Depends(get_db)):
    return reentry.resident_view(db, ctx.resident_id, _now())
