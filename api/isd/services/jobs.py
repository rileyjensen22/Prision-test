"""Jobs: listings and voluntary opt-in. Nothing here touches points, sanctions, tiers or
entitlements (invariant 7), and this module deliberately imports none of them."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from isd.models import JOB_TASK_TYPES, JobEnrollment, JobListing, WorkLog
from isd.services.audit import Actor, append_audit
from isd.services.config_store import get_current


class JobError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def pay_split(session: Session) -> dict:
    return get_current(session, "jobs").payload["pay_split"]


def list_listings(session: Session, resident_id: int) -> list[dict]:
    active_ids = set(
        session.execute(
            select(JobEnrollment.listing_id).where(
                JobEnrollment.resident_id == resident_id, JobEnrollment.status == "active"
            )
        ).scalars()
    )
    rows = session.execute(
        select(JobListing).where(JobListing.active.is_(True)).order_by(JobListing.id)
    ).scalars()
    return [
        {
            "id": j.id,
            "code": j.code,
            "title": j.title,
            "task_type": j.task_type,
            "description": j.description,
            "pay_per_task_cents": j.pay_per_task_cents,
            "enrolled": j.id in active_ids,
        }
        for j in rows
    ]


def opt_in(session: Session, resident_id: int, listing_id: int, now: datetime) -> JobEnrollment:
    job = session.get(JobListing, listing_id)
    if job is None or not job.active:
        raise JobError("NOT_FOUND", "job not found")
    if session.execute(
        select(JobEnrollment.id).where(
            JobEnrollment.resident_id == resident_id,
            JobEnrollment.listing_id == listing_id,
            JobEnrollment.status == "active",
        )
    ).first():
        raise JobError("ALREADY_JOINED", "you already joined this job")
    row = JobEnrollment(
        resident_id=resident_id, listing_id=listing_id, status="active", opted_in_at=now
    )
    session.add(row)
    session.add(WorkLog(resident_id=resident_id, listing_id=listing_id, event="joined", at=now))
    session.flush()
    return row


def leave(session: Session, resident_id: int, listing_id: int, now: datetime) -> JobEnrollment:
    row = session.execute(
        select(JobEnrollment).where(
            JobEnrollment.resident_id == resident_id,
            JobEnrollment.listing_id == listing_id,
            JobEnrollment.status == "active",
        )
    ).scalar()
    if row is None:
        raise JobError("NOT_JOINED", "you are not in this job")
    row.status, row.left_at = "left", now
    session.add(WorkLog(resident_id=resident_id, listing_id=listing_id, event="left", at=now))
    return row


# ---- staff ----
def create_listing(
    session: Session,
    actor: Actor,
    code: str,
    title: str,
    task_type: str,
    description: str,
    now: datetime,
    pay_per_task_cents: int = 0,
    partner_id: int | None = None,
):
    if task_type not in JOB_TASK_TYPES:
        raise JobError("BAD_TASK_TYPE", f"task type must be one of {', '.join(JOB_TASK_TYPES)}")
    row = JobListing(
        code=code,
        title=title,
        task_type=task_type,
        description=description,
        active=True,
        created_at=now,
        pay_per_task_cents=pay_per_task_cents,
        partner_id=partner_id,
    )
    session.add(row)
    session.flush()
    append_audit(
        session,
        actor,
        "job_listing_created",
        "job_listing",
        row.id,
        "JOB_LISTING",
        payload={"code": code, "task_type": task_type},
    )
    return row


def set_active(session: Session, actor: Actor, listing_id: int, active: bool) -> JobListing:
    row = session.get(JobListing, listing_id)
    if row is None:
        raise JobError("NOT_FOUND", "job not found")
    row.active = active
    append_audit(
        session,
        actor,
        "job_listing_changed",
        "job_listing",
        row.id,
        "JOB_LISTING",
        payload={"active": active},
    )
    return row
