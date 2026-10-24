"""Pauses staff placed on a device, read by the entitlement loader. Reads only."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from isd.models import DeviceAssignment, DeviceCommand


def locks_from_commands(cmds: list[DeviceCommand]) -> list[tuple[int, datetime, datetime]]:
    """(id, starts_at, ends_at) of each pause in one device's commands; a lift cuts it short."""
    ordered = sorted(
        (c for c in cmds if c.kind in ("lock", "unlock")), key=lambda c: (c.issued_at, c.id)
    )
    out = []
    for c in ordered:
        if c.kind == "lock":
            lifts = [
                u.issued_at for u in ordered if u.kind == "unlock" and u.issued_at > c.issued_at
            ]
            out.append((c.id, c.issued_at, min([c.ends_at, *lifts])))
    return out


def locks_for_device(session: Session, device_id: int) -> list[tuple[int, datetime, datetime]]:
    cmds = session.execute(
        select(DeviceCommand).where(DeviceCommand.device_id == device_id)
    ).scalars()
    return locks_from_commands(list(cmds))


def locks_for_residents(
    session: Session, resident_ids: list[int]
) -> dict[int, list[tuple[int, datetime, datetime]]]:
    """Pauses on the device each resident is assigned to now. Two queries however many residents."""
    pairs = session.execute(
        select(DeviceAssignment.resident_id, DeviceAssignment.device_id).where(
            DeviceAssignment.resident_id.in_(resident_ids), DeviceAssignment.ended_at.is_(None)
        )
    ).all()
    device_ids = {d for _, d in pairs}
    by_device: dict[int, list[DeviceCommand]] = {}
    if device_ids:
        for c in session.execute(
            select(DeviceCommand).where(
                DeviceCommand.device_id.in_(device_ids), DeviceCommand.kind.in_(("lock", "unlock"))
            )
        ).scalars():
            by_device.setdefault(c.device_id, []).append(c)
    out: dict[int, list[tuple[int, datetime, datetime]]] = {}
    for rid, did in pairs:
        out.setdefault(rid, []).extend(locks_from_commands(by_device.get(did, [])))
    return out
