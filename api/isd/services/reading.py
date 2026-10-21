"""Reading library (stub). Bundled public-domain texts, gated by the approved-sources allow-list."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from isd.models import ApprovedContentSource, ReadingLog
from isd.services.audit import Actor, append_audit
from isd.services.config_store import get_current
from isd.services.entitlement_service import get_entitlements

_FEATURE = {"general": "reading_general", "expanded": "reading_expanded"}


class ReadingDenied(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _items(session: Session) -> dict[str, dict]:
    return {i["id"]: i for i in get_current(session, "reading").payload["items"]}


def bundled_source_active(session: Session) -> bool:
    return (
        session.execute(
            select(ApprovedContentSource.id).where(
                ApprovedContentSource.kind == "bundled", ApprovedContentSource.active.is_(True)
            )
        ).first()
        is not None
    )


def list_items(session: Session, resident_id: int, now: datetime) -> list[dict]:
    ent = get_entitlements(session, resident_id, now)
    approved = bundled_source_active(session)
    out = []
    for i in _items(session).values():
        fe = ent.features[_FEATURE[i["catalog"]]]
        out.append(
            {
                "id": i["id"],
                "title": i["title"],
                "author": i["author"],
                "catalog": i["catalog"],
                "allowed": fe.allowed and approved,
                "reasons": [{"code": r.code, "params": r.params} for r in fe.reasons],
            }
        )
    return out


def read_item(session: Session, resident_id: int, item_id: str, now: datetime) -> dict:
    item = _items(session).get(item_id)
    if item is None:
        raise ReadingDenied("NOT_FOUND", "text not found")
    if not bundled_source_active(session):
        raise ReadingDenied("SOURCE_NOT_APPROVED", "this content source is not approved")
    if not get_entitlements(session, resident_id, now).features[_FEATURE[item["catalog"]]].allowed:
        raise ReadingDenied("FEATURE_LOCKED", "this text is locked")
    session.add(ReadingLog(resident_id=resident_id, item_id=item_id, at=now))
    session.flush()
    return {k: item[k] for k in ("id", "title", "author", "language", "text")}


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
