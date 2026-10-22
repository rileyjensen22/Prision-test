"""Commissary and the append-only trust ledger. Money is integer cents."""

from datetime import datetime

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from isd.engine.commissary import OrderError, check_order, item_block_reason, price_order
from isd.interfaces.payments import PaymentProvider
from isd.models import CommissaryOrder, CommissaryOrderLine, Resident, TrustLedger
from isd.providers import get_payments
from isd.services.audit import Actor, append_audit
from isd.services.config_store import get_current
from isd.services.entitlement_service import get_entitlements
from isd.services.ledger import balance_cents, post_ledger  # noqa: F401 (re-exported)
from isd.services.usage import spent_cents_this_week


def _config(session: Session) -> dict:
    return get_current(session, "commissary").payload


def _catalog(session: Session) -> dict[str, dict]:
    return {i["code"]: i for i in _config(session)["items"]}


def deposit(
    session: Session,
    actor: Actor,
    resident_id: int,
    amount_cents: int,
    payer_ref: str,
    idempotency_key: str,
    now: datetime,
    payments: PaymentProvider | None = None,
) -> TrustLedger:
    """Simulated family deposit through the PaymentProvider interface. Idempotent per key."""
    if not 0 < amount_cents <= _config(session)["max_deposit_cents"]:
        raise OrderError("BAD_AMOUNT", "deposit amount out of range")
    resident = session.get(Resident, resident_id)
    if resident is None:
        raise LookupError("resident not found")
    result = (payments or get_payments()).create_deposit(
        resident.code, amount_cents, payer_ref, idempotency_key
    )
    if result.status != "completed":
        raise OrderError("PAYMENT_FAILED", "deposit did not complete")
    existing = session.execute(
        select(TrustLedger).where(TrustLedger.ref == result.external_id)
    ).scalar()
    if existing:
        return existing
    row = post_ledger(
        session,
        resident_id,
        "deposit",
        amount_cents,
        now,
        ref=result.external_id,
        memo="family deposit (mock)",
        created_by=actor.id,
    )
    append_audit(
        session,
        actor,
        "deposit",
        "resident",
        resident.code,
        "DEPOSIT",
        payload={"amount_cents": amount_cents, "ref": result.external_id},
    )
    return row


def catalog_view(session: Session, resident_id: int, now: datetime) -> dict:
    ent = get_entitlements(session, resident_id, now)
    fe = ent.features["commissary"]
    limit_cents = fe.limits.get("dollars_per_week", 0) * 100
    spent = spent_cents_this_week(session, resident_id, now)
    items = []
    for i in _config(session)["items"]:
        block = item_block_reason(i, ent.effective_tier, ent.offense_categories)
        items.append(
            {
                "code": i["code"],
                "name": i["name"],
                "price_cents": i["price_cents"],
                "category": i["category"],
                "min_tier": i["min_tier"],
                "available": fe.allowed and block is None,
                "block_reason": None if block is None else block,
            }
        )
    return {
        "allowed": fe.allowed,
        "reasons": [{"code": r.code, "ends_at": r.ends_at, "params": r.params} for r in fe.reasons],
        "balance_cents": balance_cents(session, resident_id),
        "weekly_limit_cents": limit_cents,
        "spent_this_week_cents": spent,
        "items": items,
    }


def place_order(
    session: Session, resident_id: int, lines: dict[str, int], client_id: str, now: datetime
) -> CommissaryOrder:
    existing = session.execute(
        select(CommissaryOrder).where(CommissaryOrder.client_id == client_id)
    ).scalar()
    if existing:
        if existing.resident_id != resident_id:
            raise OrderError("DUPLICATE", "order id already used")
        return existing
    session.execute(text("SELECT pg_advisory_xact_lock(2, :r)"), {"r": resident_id})
    ent = get_entitlements(session, resident_id, now)
    fe = ent.features["commissary"]
    if not fe.allowed:
        raise OrderError("FEATURE_LOCKED", "commissary is locked")
    catalog = _catalog(session)
    total = price_order(lines, catalog)
    for code in lines:
        block = item_block_reason(catalog[code], ent.effective_tier, ent.offense_categories)
        if block:
            raise OrderError(block, f"{code} is not available to you")
    check_order(
        total,
        balance_cents(session, resident_id),
        fe.limits["dollars_per_week"] * 100,
        spent_cents_this_week(session, resident_id, now),
    )
    order = CommissaryOrder(
        resident_id=resident_id, client_id=client_id, total_cents=total, created_at=now
    )
    session.add(order)
    session.flush()
    for code, qty in lines.items():
        session.add(
            CommissaryOrderLine(
                order_id=order.id,
                item_code=code,
                qty=qty,
                unit_price_cents=catalog[code]["price_cents"],
            )
        )
    post_ledger(session, resident_id, "purchase", -total, now, order_id=order.id, memo="commissary")
    return order


def verify_ledgers(session: Session) -> list[str]:
    """Returns a list of problems; empty means every resident's ledger is consistent."""
    problems = []
    running: dict[int, int] = {}
    for e in session.execute(select(TrustLedger).order_by(TrustLedger.id)).scalars():
        expected = running.get(e.resident_id, 0) + e.amount_cents
        if e.balance_after_cents != expected:
            problems.append(f"entry {e.id}: balance {e.balance_after_cents} != {expected}")
        running[e.resident_id] = e.balance_after_cents
    for o in session.execute(select(CommissaryOrder)).scalars():
        spent = -sum(
            e.amount_cents
            for e in session.execute(
                select(TrustLedger).where(TrustLedger.order_id == o.id)
            ).scalars()
        )
        if spent != o.total_cents:
            problems.append(f"order {o.id}: ledger {spent} != total {o.total_cents}")
    return problems
