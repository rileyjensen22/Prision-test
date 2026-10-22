"""The append-only trust-account ledger. Money is integer cents.

Kept apart from commissary (and from anything that decides entitlements) so that other money
paths, such as work pay, can post to it without depending on shopping rules.
"""

from datetime import datetime

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from isd.engine.commissary import OrderError
from isd.models import TrustLedger


def balance_cents(session: Session, resident_id: int) -> int:
    return (
        session.execute(
            select(TrustLedger.balance_after_cents)
            .where(TrustLedger.resident_id == resident_id)
            .order_by(TrustLedger.id.desc())
            .limit(1)
        ).scalar()
        or 0
    )


def post_ledger(
    session: Session,
    resident_id: int,
    entry_type: str,
    amount_cents: int,
    now: datetime,
    *,
    ref: str | None = None,
    order_id: int | None = None,
    memo: str | None = None,
    created_by: int | None = None,
) -> TrustLedger:
    # One writer per resident at a time, so balance_after is always consistent.
    session.execute(text("SELECT pg_advisory_xact_lock(2, :r)"), {"r": resident_id})
    new_balance = balance_cents(session, resident_id) + amount_cents
    if new_balance < 0:
        raise OrderError("INSUFFICIENT_FUNDS", "not enough money in your account")
    row = TrustLedger(
        resident_id=resident_id,
        entry_type=entry_type,
        amount_cents=amount_cents,
        balance_after_cents=new_balance,
        ref=ref,
        order_id=order_id,
        memo=memo,
        created_by=created_by,
        created_at=now,
    )
    session.add(row)
    session.flush()
    return row
