"""Append-only, hash-chained audit log (invariant 3).

Entries are never edited. A mistake is fixed with a new `correction` entry whose `ref_seq`
points at the original. Payloads must not contain floats (JSONB round-trip must be stable).
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from isd.models import AuditLog

GENESIS_HASH = "0" * 64
_CHAIN_LOCK_KEY = 727001


@dataclass(frozen=True)
class Actor:
    id: int | None
    role: str  # staff role, or "system"


SYSTEM = Actor(None, "system")


def _canonical_ts(ts: datetime) -> str:
    return ts.astimezone(UTC).isoformat(timespec="microseconds")


def compute_hash(prev_hash: str, entry: dict[str, Any]) -> str:
    body = json.dumps(entry, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256((prev_hash + body).encode()).hexdigest()


def _entry_fields(row: AuditLog) -> dict[str, Any]:
    return {
        "seq": row.seq,
        "ts": _canonical_ts(row.ts),
        "actor_id": row.actor_id,
        "actor_role": row.actor_role,
        "action": row.action,
        "target_type": row.target_type,
        "target_id": row.target_id,
        "reason_code": row.reason_code,
        "ref_seq": row.ref_seq,
        "payload": row.payload,
    }


def append_audit(
    session: Session,
    actor: Actor,
    action: str,
    target_type: str,
    target_id: str | int,
    reason_code: str | None = None,
    ref_seq: int | None = None,
    payload: dict[str, Any] | None = None,
) -> AuditLog:
    # Serialise writers so the chain has no forks; released at commit/rollback.
    session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _CHAIN_LOCK_KEY})
    last = session.execute(select(AuditLog).order_by(AuditLog.seq.desc()).limit(1)).scalar()
    row = AuditLog(
        seq=(last.seq + 1) if last else 1,
        ts=datetime.now(UTC),
        actor_id=actor.id,
        actor_role=actor.role,
        action=action,
        target_type=target_type,
        target_id=str(target_id),
        reason_code=reason_code,
        ref_seq=ref_seq,
        payload=payload or {},
        prev_hash=last.hash if last else GENESIS_HASH,
        hash="",
    )
    row.hash = compute_hash(row.prev_hash, _entry_fields(row))
    session.add(row)
    session.flush()
    return row


@dataclass(frozen=True)
class ChainResult:
    ok: bool
    entries: int
    first_bad_seq: int | None = None
    problem: str | None = None


def verify_chain(session: Session) -> ChainResult:
    rows = session.execute(select(AuditLog).order_by(AuditLog.seq)).scalars()
    prev_hash, expected_seq, count = GENESIS_HASH, 1, 0
    for row in rows:
        if row.seq != expected_seq:
            return ChainResult(False, count, row.seq, "sequence gap or reorder")
        if row.prev_hash != prev_hash:
            return ChainResult(False, count, row.seq, "prev_hash does not match previous entry")
        if row.hash != compute_hash(row.prev_hash, _entry_fields(row)):
            return ChainResult(False, count, row.seq, "entry content does not match its hash")
        prev_hash, expected_seq, count = row.hash, expected_seq + 1, count + 1
    return ChainResult(True, count)
