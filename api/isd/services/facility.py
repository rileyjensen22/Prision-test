"""Ingest events from the facility's systems. Idempotent by event_id."""

from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from isd.engine.authority import Evidence
from isd.interfaces.facility import FacilityEventIn
from isd.models import Cell, DeviceAssignment, FacilityEvent, Resident
from isd.services import out_of_cell, sanctions
from isd.services.audit import SYSTEM


def _resident_in_cell(session: Session, cell_code: str) -> int | None:
    return session.execute(
        select(DeviceAssignment.resident_id)
        .join(Cell, Cell.id == DeviceAssignment.cell_id)
        .where(Cell.code == cell_code, DeviceAssignment.ended_at.is_(None))
    ).scalar()


def ingest(session: Session, ev: FacilityEventIn, now: datetime) -> str:
    existing = session.execute(
        select(FacilityEvent).where(FacilityEvent.event_id == ev.event_id)
    ).scalar()
    if existing:
        return existing.result
    result = _handle(session, ev, now)
    session.add(
        FacilityEvent(
            event_id=ev.event_id, type=ev.type, payload=ev.payload, received_at=now, result=result
        )
    )
    session.flush()
    return result


def _handle(session: Session, ev: FacilityEventIn, now: datetime) -> str:
    if ev.type == "camera_obstruction":
        rid = _resident_in_cell(session, str(ev.payload.get("cell", "")))
        if rid is None:
            return "ignored:no resident in that cell"
        # The system-detected event is the evidence; a supervisor must still confirm it.
        s = sanctions.issue_sanction(
            session, SYSTEM, rid, "CAM_BLOCK", now, Evidence("system_event", ref=ev.event_id)
        )
        return f"sanction:{s.id}:{s.status}"
    if ev.type == "out_of_cell":
        code = str(ev.payload.get("resident_code", ""))
        resident = session.execute(select(Resident).where(Resident.code == code)).scalar()
        if resident is None:
            return "ignored:unknown resident"
        out_of_cell.record(
            session,
            SYSTEM,
            resident.id,
            date.fromisoformat(ev.payload["day"]),
            int(ev.payload["minutes"]),
            "ingest",
            now,
        )
        return "out_of_cell:recorded"
    return "ignored:unknown type"
