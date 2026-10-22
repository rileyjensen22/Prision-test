"""Doing work: getting a task, handing it in, being paid. Tasks come from a partner (a mock in v1).

Nothing here touches points, sanctions, tiers or entitlements (invariant 7). The one outside
influence is `job_policy`, which only does anything when the operator turns it on.
"""

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from isd.engine.periods import period_start
from isd.models import (
    JobEnrollment,
    JobListing,
    JobPartner,
    JobTask,
    TaskSubmission,
    WorkLog,
)
from isd.providers import get_job_partner
from isd.services import earnings, job_policy
from isd.services.config_store import get_current
from isd.services.jobs import JobError
from isd.work_rules import public_view, validate_task_spec

TARGET_OPEN = 12  # how many unclaimed tasks to keep ready per listing


def _cfg(session: Session) -> dict:
    return get_current(session, "jobs").payload


def sync_tasks(session: Session, listing: JobListing, now: datetime) -> int:
    """Tops up the listing's open tasks from its partner. Content is screened on the way in."""
    if listing.partner_id is None:
        return 0
    partner = session.get(JobPartner, listing.partner_id)
    open_now = session.execute(
        select(func.count()).where(JobTask.listing_id == listing.id, JobTask.status == "open")
    ).scalar()
    want = TARGET_OPEN - open_now
    if want <= 0 or partner is None or not partner.active:
        return 0
    have = session.execute(select(func.count()).where(JobTask.listing_id == listing.id)).scalar()
    added = 0
    for spec in get_job_partner(partner.code).fetch_tasks(listing.task_type, want, have):
        external_id = spec["external_id"]
        content = {k: v for k, v in spec.items() if k != "external_id"}
        validate_task_spec(listing.task_type, content)  # refuses anything that looks personal
        session.add(
            JobTask(
                listing_id=listing.id,
                external_id=external_id,
                kind=listing.task_type,
                spec=content,
                status="open",
                created_at=now,
            )
        )
        added += 1
    session.flush()
    return added


def sync_all(session: Session, now: datetime) -> int:
    listings = session.execute(select(JobListing).where(JobListing.active.is_(True))).scalars()
    return sum(sync_tasks(session, j, now) for j in list(listings))


def _enrolled(session: Session, resident_id: int, listing_id: int) -> bool:
    return (
        session.execute(
            select(JobEnrollment.id).where(
                JobEnrollment.resident_id == resident_id,
                JobEnrollment.listing_id == listing_id,
                JobEnrollment.status == "active",
            )
        ).first()
        is not None
    )


def _done_today(session: Session, resident_id: int, now: datetime) -> int:
    return session.execute(
        select(func.count()).where(
            TaskSubmission.resident_id == resident_id,
            TaskSubmission.submitted_at >= period_start(now, "day"),
            TaskSubmission.submitted_at <= now,
        )
    ).scalar()


def _release_stale(session: Session, listing_id: int, now: datetime) -> None:
    cutoff = now - timedelta(minutes=_cfg(session)["claim_minutes"])
    for t in session.execute(
        select(JobTask)
        .where(
            JobTask.listing_id == listing_id,
            JobTask.status == "claimed",
            JobTask.claimed_at < cutoff,
        )
        .with_for_update()
    ).scalars():
        t.status, t.claimed_by, t.claimed_at = "open", None, None


def _view(task: JobTask, listing: JobListing, expires_at: datetime) -> dict:
    return {
        "task_id": task.id,
        "listing_id": listing.id,
        "kind": task.kind,
        "task": public_view(task.kind, task.spec),
        "pay_cents": listing.pay_per_task_cents,
        "expires_at": expires_at.isoformat(),
    }


def next_task(session: Session, resident_id: int, listing_id: int, now: datetime) -> dict:
    listing = session.get(JobListing, listing_id)
    if listing is None or not listing.active:
        raise JobError("NOT_FOUND", "job not found")
    if not _enrolled(session, resident_id, listing_id):
        raise JobError("NOT_JOINED", "join this job first")
    pause = job_policy.suspension(session, resident_id, now)
    if pause:
        raise JobError("JOB_SUSPENDED", "work is paused while a sanction is active")
    cfg = _cfg(session)
    if _done_today(session, resident_id, now) >= cfg["max_tasks_per_day"]:
        raise JobError("DAILY_CAP", "that is the most tasks for one day; come back tomorrow")
    _release_stale(session, listing_id, now)
    claim = timedelta(minutes=cfg["claim_minutes"])
    mine = session.execute(
        select(JobTask).where(
            JobTask.listing_id == listing_id,
            JobTask.status == "claimed",
            JobTask.claimed_by == resident_id,
        )
    ).scalar()
    if mine:
        return _view(mine, listing, mine.claimed_at + claim)
    for _ in range(2):  # the second pass is after topping up from the partner
        task = session.execute(
            select(JobTask)
            .where(JobTask.listing_id == listing_id, JobTask.status == "open")
            .order_by(JobTask.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        ).scalar()
        if task:
            task.status, task.claimed_by, task.claimed_at = "claimed", resident_id, now
            session.flush()
            return _view(task, listing, now + claim)
        if not sync_tasks(session, listing, now):
            break
    raise JobError("NO_TASKS", "there is no work right now; check back later")


def submit(session: Session, resident_id: int, task_id: int, answer: str, now: datetime) -> dict:
    task = session.execute(select(JobTask).where(JobTask.id == task_id).with_for_update()).scalar()
    if task is None or task.claimed_by != resident_id:
        raise JobError("NOT_FOUND", "task not found")
    if task.status != "claimed":
        raise JobError("ALREADY_DONE", "this task was already handed in")
    cfg = _cfg(session)
    if now > task.claimed_at + timedelta(minutes=cfg["claim_minutes"]):
        task.status, task.claimed_by, task.claimed_at = "open", None, None
        raise JobError("EXPIRED", "this task timed out; get a new one")
    listing = session.get(JobListing, task.listing_id)
    if not _enrolled(session, resident_id, listing.id):
        raise JobError("NOT_JOINED", "you are not in this job")
    if job_policy.suspension(session, resident_id, now):
        raise JobError("JOB_SUSPENDED", "work is paused while a sanction is active")
    partner = session.get(JobPartner, listing.partner_id)
    review = get_job_partner(partner.code).review(
        task.kind, task.spec, answer, cfg["accept_similarity"]
    )
    pay = listing.pay_per_task_cents if review.accepted else 0
    sub = TaskSubmission(
        task_id=task.id,
        resident_id=resident_id,
        listing_id=listing.id,
        answer=answer.strip() if review.accepted else None,  # nothing is kept from a refusal
        accepted=review.accepted,
        review_reason=review.reason,
        pay_cents=pay,
        submitted_at=now,
    )
    session.add(sub)
    session.flush()
    task.status = "accepted" if review.accepted else "rejected"
    session.add(
        WorkLog(
            resident_id=resident_id,
            listing_id=listing.id,
            event="task_accepted" if review.accepted else "task_rejected",
            task_id=task.id,
            at=now,
        )
    )
    earned = 0
    if review.accepted and pay > 0:
        earned = earnings.record_earning(session, resident_id, sub, now).resident_cents
    session.flush()
    return {"accepted": review.accepted, "reason": review.reason, "earned_cents": earned}


def work_log(session: Session, resident_id: int, limit: int = 50) -> list[dict]:
    rows = session.execute(
        select(WorkLog, JobListing.title)
        .join(JobListing, JobListing.id == WorkLog.listing_id)
        .where(WorkLog.resident_id == resident_id)
        .order_by(WorkLog.id.desc())
        .limit(limit)
    ).all()
    return [{"event": w.event, "job": title, "at": w.at.isoformat()} for w, title in rows]
