"""Work earnings: the split, the append-only earnings ledger, and payouts to the trust account."""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from isd.models import EarningsLedger, JobEnrollment, TaskSubmission
from isd.services.config_store import get_current
from isd.services.ledger import post_ledger
from isd.work_rules import split_pay


def _cfg(session: Session) -> dict:
    return get_current(session, "jobs").payload


def record_earning(
    session: Session, resident_id: int, submission: TaskSubmission, now: datetime
) -> EarningsLedger:
    split = _cfg(session)["pay_split"]
    resident, facility, deductions = split_pay(
        submission.pay_cents, split["resident_pct"], split["facility_pct"], split["deductions_pct"]
    )
    row = EarningsLedger(
        resident_id=resident_id,
        entry_type="earned",
        submission_id=submission.id,
        gross_cents=submission.pay_cents,
        resident_cents=resident,
        facility_cents=facility,
        deductions_cents=deductions,
        split=dict(split),  # the split in force when it was earned
        created_at=now,
    )
    session.add(row)
    session.flush()
    return row


def pending_cents(session: Session, resident_id: int) -> int:
    """Earned but not yet paid into the trust account."""
    return int(
        session.execute(
            select(func.coalesce(func.sum(EarningsLedger.resident_cents), 0)).where(
                EarningsLedger.resident_id == resident_id
            )
        ).scalar()
        or 0
    )


def summary(session: Session, resident_id: int) -> dict:
    earned, paid = session.execute(
        select(
            func.coalesce(
                func.sum(EarningsLedger.resident_cents).filter(
                    EarningsLedger.entry_type == "earned"
                ),
                0,
            ),
            func.coalesce(
                -func.sum(EarningsLedger.resident_cents).filter(
                    EarningsLedger.entry_type == "payout"
                ),
                0,
            ),
        ).where(EarningsLedger.resident_id == resident_id)
    ).one()
    return {
        "earned_cents": int(earned),
        "paid_cents": int(paid),
        "pending_cents": int(earned - paid),
    }


def pay_out(session: Session, resident_id: int, now: datetime) -> EarningsLedger | None:
    """Moves what a resident has earned into their trust account. Safe to repeat."""
    owed = pending_cents(session, resident_id)
    if owed < _cfg(session)["min_payout_cents"]:
        return None
    last = session.execute(
        select(func.max(EarningsLedger.id)).where(EarningsLedger.resident_id == resident_id)
    ).scalar()
    trust = post_ledger(
        session,
        resident_id,
        "job_payout",
        owed,
        now,
        ref=f"jobpay-{resident_id}-{last}",
        memo="work earnings",
    )
    row = EarningsLedger(
        resident_id=resident_id,
        entry_type="payout",
        gross_cents=0,
        resident_cents=-owed,
        facility_cents=0,
        deductions_cents=0,
        trust_ledger_id=trust.id,
        created_at=now,
    )
    session.add(row)
    session.flush()
    return row


def pay_out_all(session: Session, now: datetime) -> int:
    ids = session.execute(
        select(EarningsLedger.resident_id).group_by(EarningsLedger.resident_id)
    ).scalars()
    return sum(1 for rid in list(ids) if pay_out(session, rid, now) is not None)


def partner_dashboard(session: Session) -> list[dict]:
    """What a partner would see: totals per listing. No resident is named or counted by name."""
    from isd.models import JobListing, JobPartner

    rows = []
    for listing, partner in session.execute(
        select(JobListing, JobPartner)
        .join(JobPartner, JobPartner.id == JobListing.partner_id, isouter=True)
        .order_by(JobListing.id)
    ).all():
        subs = session.execute(
            select(
                func.count().filter(TaskSubmission.accepted.is_(True)),
                func.count().filter(TaskSubmission.accepted.is_(False)),
            ).where(TaskSubmission.listing_id == listing.id)
        ).one()
        owed = session.execute(
            select(
                func.coalesce(func.sum(EarningsLedger.gross_cents), 0),
                func.coalesce(func.sum(EarningsLedger.facility_cents), 0),
                func.coalesce(func.sum(EarningsLedger.deductions_cents), 0),
            )
            .join(TaskSubmission, TaskSubmission.id == EarningsLedger.submission_id)
            .where(TaskSubmission.listing_id == listing.id)
        ).one()
        working = session.execute(
            select(func.count()).where(
                JobEnrollment.listing_id == listing.id, JobEnrollment.status == "active"
            )
        ).scalar()
        rows.append(
            {
                "listing_id": listing.id,
                "code": listing.code,
                "title": listing.title,
                "partner": partner.name if partner else None,
                "pay_per_task_cents": listing.pay_per_task_cents,
                "participants": working,
                "tasks_accepted": subs[0],
                "tasks_rejected": subs[1],
                "payouts_owed_cents": int(owed[0]),  # gross pay due for accepted work
                "facility_share_cents": int(owed[1]),
                "deductions_cents": int(owed[2]),
            }
        )
    return rows
