"""Reading library: bundled public-domain texts, gated by entitlements and approved sources.

Legal and religious texts are protected baseline (invariant 1): they ignore tier, sanctions and the
allow-list. Progress and bookmarks are the resident's own and are never shown to staff.
"""

from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from isd.engine.reading import (
    BASELINE_CATALOGS,
    CATALOG_FEATURE,
    clamp_page,
    is_complete,
    paginate,
)
from isd.models import (
    ApprovedContentSource,
    PointEvent,
    ReadingBookmark,
    ReadingLog,
    ReadingProgress,
)
from isd.services.audit import SYSTEM, Actor, append_audit
from isd.services.config_store import get_current
from isd.services.entitlement_service import get_entitlements, load_engine_config
from isd.services.points import add_point_event

BASELINE_LOG_ID = "baseline"  # what staff-visible usage records for legal/religious reading say


class ReadingDenied(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _items(session: Session) -> dict[str, dict]:
    return {i["id"]: i for i in get_current(session, "reading").payload["items"]}


def _active_sources(session: Session) -> set[str]:
    return set(
        session.execute(
            select(ApprovedContentSource.name).where(ApprovedContentSource.active.is_(True))
        ).scalars()
    )


def bundled_source_active(session: Session) -> bool:
    return (
        session.execute(
            select(ApprovedContentSource.id).where(
                ApprovedContentSource.kind == "bundled", ApprovedContentSource.active.is_(True)
            )
        ).first()
        is not None
    )


def _can_read(item: dict, ent, sources: set[str]):
    """Returns (allowed, reasons, approved); baseline catalogs skip the allow-list."""
    fe = ent.features[CATALOG_FEATURE[item["catalog"]]]
    approved = item["catalog"] in BASELINE_CATALOGS or item["source"] in sources
    return fe.allowed and approved, fe.reasons, approved


def _progress(session: Session, resident_id: int) -> dict[str, ReadingProgress]:
    rows = session.execute(
        select(ReadingProgress).where(ReadingProgress.resident_id == resident_id)
    ).scalars()
    return {r.item_id: r for r in rows}


def _bookmarks(session: Session, resident_id: int, item_id: str | None = None) -> dict:
    q = select(ReadingBookmark).where(ReadingBookmark.resident_id == resident_id)
    if item_id:
        q = q.where(ReadingBookmark.item_id == item_id)
    out: dict[str, list[int]] = {}
    for b in session.execute(q.order_by(ReadingBookmark.page)).scalars():
        out.setdefault(b.item_id, []).append(b.page)
    return out


def list_items(session: Session, resident_id: int, now: datetime) -> list[dict]:
    ent = get_entitlements(session, resident_id, now)
    sources = _active_sources(session)
    progress = _progress(session, resident_id)
    marks = _bookmarks(session, resident_id)
    out = []
    for i in _items(session).values():
        allowed, reasons, _ = _can_read(i, ent, sources)
        p = progress.get(i["id"])
        out.append(
            {
                "id": i["id"],
                "title": i["title"],
                "author": i["author"],
                "catalog": i["catalog"],
                "feature": CATALOG_FEATURE[i["catalog"]],
                "language": i["language"],
                "pages": len(paginate(i["text"])),
                "page": p.page if p else 0,
                "completed": bool(p and p.completed_at),
                "bookmarks": len(marks.get(i["id"], [])),
                "allowed": allowed,
                "reasons": [{"code": r.code, "params": r.params} for r in reasons],
            }
        )
    return out


def _open(session: Session, resident_id: int, item_id: str, now: datetime) -> dict:
    item = _items(session).get(item_id)
    if item is None:
        raise ReadingDenied("NOT_FOUND", "text not found")
    allowed, _, approved = _can_read(
        item, get_entitlements(session, resident_id, now), _active_sources(session)
    )
    if not approved:
        raise ReadingDenied("SOURCE_NOT_APPROVED", "this content source is not approved")
    if not allowed:
        raise ReadingDenied("FEATURE_LOCKED", "this text is locked")
    return item


def read_item(session: Session, resident_id: int, item_id: str, now: datetime) -> dict:
    item = _open(session, resident_id, item_id, now)
    # Staff-visible usage never names a legal or religious text (what someone reads for their
    # case or faith is theirs), but it still counts as activity for the welfare check.
    logged = BASELINE_LOG_ID if item["catalog"] in BASELINE_CATALOGS else item_id
    session.add(ReadingLog(resident_id=resident_id, item_id=logged, at=now))
    session.flush()
    p = session.execute(
        select(ReadingProgress).where(
            ReadingProgress.resident_id == resident_id, ReadingProgress.item_id == item_id
        )
    ).scalar()
    pages = paginate(item["text"])
    return {
        "id": item["id"],
        "title": item["title"],
        "author": item["author"],
        "language": item["language"],
        "text": item["text"],
        "pages": pages,
        "page": clamp_page(p.page if p else 0, len(pages)),
        "completed": bool(p and p.completed_at),
        "bookmarks": _bookmarks(session, resident_id, item_id).get(item_id, []),
    }


def _award_completion(session: Session, resident_id: int, now: datetime) -> int:
    """Points for finishing a text; 0 by default. Over the weekly cap just means no points."""
    if not load_engine_config(session).point_events["book_completed"]["points"]:
        return 0  # a zero-point event would only add noise to the record
    try:
        ev: PointEvent = add_point_event(session, SYSTEM, resident_id, "book_completed", now)
    except ValueError:
        return 0
    return ev.points


def save_progress(
    session: Session, resident_id: int, item_id: str, page: int, now: datetime
) -> dict:
    """Moves progress forward only, so replaying an old queued event can never undo reading."""
    item = _open(session, resident_id, item_id, now)
    total = len(paginate(item["text"]))
    page = clamp_page(page, total)
    row = session.execute(
        select(ReadingProgress)
        .where(ReadingProgress.resident_id == resident_id, ReadingProgress.item_id == item_id)
        .with_for_update()
    ).scalar()
    if row is None:
        row = ReadingProgress(resident_id=resident_id, item_id=item_id, page=0, updated_at=now)
        session.add(row)
    row.page = max(row.page, page)
    row.updated_at = now
    awarded = 0
    if row.completed_at is None and is_complete(row.page, total):
        row.completed_at = now
        awarded = _award_completion(session, resident_id, now)
    session.flush()
    return {"page": row.page, "completed": row.completed_at is not None, "points_awarded": awarded}


def set_bookmark(
    session: Session, resident_id: int, item_id: str, page: int, on: bool, now: datetime
) -> dict:
    item = _open(session, resident_id, item_id, now)
    total = len(paginate(item["text"]))
    if not 0 <= page < total:
        raise ReadingDenied("BAD_PAGE", "no such page")
    where = (
        ReadingBookmark.resident_id == resident_id,
        ReadingBookmark.item_id == item_id,
        ReadingBookmark.page == page,
    )
    exists = session.execute(select(ReadingBookmark.id).where(*where)).first() is not None
    if on and not exists:
        session.add(ReadingBookmark(resident_id=resident_id, item_id=item_id, page=page))
    elif not on and exists:
        session.execute(delete(ReadingBookmark).where(*where))
    session.flush()
    return {"bookmarks": _bookmarks(session, resident_id, item_id).get(item_id, [])}


# ---- staff: the allow-list ----
def list_sources(session: Session) -> list[ApprovedContentSource]:
    return list(
        session.execute(select(ApprovedContentSource).order_by(ApprovedContentSource.id)).scalars()
    )


def add_source(
    session: Session, actor: Actor, name: str, kind: str, base_url: str | None, now: datetime
):
    if kind == "external" and not (base_url or "").startswith("https://"):
        raise ValueError("external sources need an https:// base URL")
    row = ApprovedContentSource(
        name=name, kind=kind, base_url=base_url, active=True, approved_by=actor.id, approved_at=now
    )
    session.add(row)
    session.flush()
    append_audit(
        session,
        actor,
        "content_source_added",
        "content_source",
        row.id,
        "CONTENT_SOURCE",
        payload={"name": name, "kind": kind, "base_url": base_url},
    )
    return row


def set_source_active(session: Session, actor: Actor, source_id: int, active: bool):
    row = session.get(ApprovedContentSource, source_id)
    if row is None:
        raise LookupError("source not found")
    if row.protected and not active:
        raise ValueError("this source holds protected baseline texts and cannot be switched off")
    row.active = active
    append_audit(
        session,
        actor,
        "content_source_changed",
        "content_source",
        row.id,
        "CONTENT_SOURCE",
        payload={"active": active},
    )
    return row
