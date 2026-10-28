"""The facility model: site, hubs, lines, floors, cells and recreation rooms, and the grouped
numbers the dashboard shows. The numbers come from aggregate queries (a fixed number however many
residents there are); nothing here computes entitlements per resident."""

from collections.abc import Iterable, Iterator
from datetime import datetime, timedelta

from sqlalchemy import and_, distinct, func, select
from sqlalchemy.orm import Session

from isd.models import (
    Cell,
    Device,
    DeviceAssignment,
    Floor,
    Hub,
    Line,
    RecArea,
    Sanction,
    Site,
)
from isd.services.config_store import get_current


class FacilityError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def settings(session: Session) -> dict:
    return get_current(session, "facility").payload


def scale_named(session: Session, name: str | None = None) -> dict:
    cfg = settings(session)
    scale = name or cfg["default_scale"]
    if scale not in cfg["scales"]:
        raise FacilityError("BAD_SCALE", f"unknown scale {scale!r}")
    return cfg["scales"][scale]


def _names(codes: Iterable[str] | None) -> Iterator[str | None]:
    yield from codes or ()
    while True:
        yield None


def build(session: Session, scale: dict, cell_codes: Iterable[str] | None = None) -> list[Cell]:
    """Creates the site, hubs, lines, floors, recreation rooms and (empty) cells. Cells take their
    names from `cell_codes` first, then `<line>-F<floor>-C<nn>`. Refuses to run twice."""
    if session.execute(select(Site.id)).first():
        raise FacilityError("EXISTS", "the facility has already been built")
    cfg = settings(session)
    site = Site(code=cfg["site"]["code"], name=cfg["site"]["name"])
    session.add(site)
    session.flush()
    names = _names(cell_codes)
    cells: list[Cell] = []
    for h in range(1, scale["hubs"] + 1):
        hub = Hub(site_id=site.id, code=f"H{h}", name=f"Hub {h}")
        session.add(hub)
        session.flush()
        for ln in range(1, scale["lines_per_hub"] + 1):
            line = Line(hub_id=hub.id, code=f"H{h}-L{ln}", name=f"Line {ln}")
            session.add(line)
            session.flush()
            for n in range(1, cfg["rec"]["rooms_per_line"] + 1):
                session.add(
                    RecArea(
                        line_id=line.id,
                        code=f"{line.code}-IN{n}",
                        name=f"Day room {n}",
                        kind="indoor",
                    )
                )
            for n in range(1, cfg["rec"]["outdoor_rooms_per_line"] + 1):
                session.add(
                    RecArea(
                        line_id=line.id,
                        code=f"{line.code}-OUT{n}",
                        name=f"Yard {n}",
                        kind="outdoor",
                    )
                )
            for level in range(1, scale["floors_per_line"] + 1):
                floor = Floor(line_id=line.id, level=level)
                session.add(floor)
                session.flush()
                for c in range(1, scale["cells_per_floor"] + 1):
                    code = next(names) or f"{line.code}-F{level}-C{c:02d}"
                    cell = Cell(code=code, unit=line.code, line_code=line.code, floor_id=floor.id)
                    session.add(cell)
                    cells.append(cell)
    session.flush()
    return cells


def line_of_unit(session: Session, unit: str) -> Line | None:
    return session.execute(select(Line).where(Line.code == unit)).scalar()


def floor_levels(session: Session, line_id: int) -> list[int]:
    return list(
        session.execute(select(Floor.level).where(Floor.line_id == line_id).order_by(Floor.level))
        .scalars()
        .all()
    )


def rec_areas(session: Session, line_id: int, kind: str) -> list[RecArea]:
    return list(
        session.execute(
            select(RecArea)
            .where(RecArea.line_id == line_id, RecArea.kind == kind)
            .order_by(RecArea.id)
        )
        .scalars()
        .all()
    )


def floor_of_resident(session: Session, resident_id: int) -> int:
    """The floor level of the resident's cell, 0 when the cell is not on a floor."""
    level = session.execute(
        select(Floor.level)
        .join(Cell, Cell.floor_id == Floor.id)
        .join(DeviceAssignment, DeviceAssignment.cell_id == Cell.id)
        .where(DeviceAssignment.resident_id == resident_id, DeviceAssignment.ended_at.is_(None))
        .limit(1)
    ).scalar()
    return level or 0


def overview(session: Session, now: datetime, offline_after: timedelta) -> dict:
    """Hub, line and floor numbers in one query: cells, occupied cells, devices that have not
    checked in for `offline_after`, and residents with an active sanction."""
    cut = now - offline_after
    open_a = and_(DeviceAssignment.cell_id == Cell.id, DeviceAssignment.ended_at.is_(None))
    rows = session.execute(
        select(
            Hub.code,
            Line.code,
            Floor.level,
            func.count(distinct(Cell.id)),
            func.count(distinct(DeviceAssignment.id)),
            func.count(distinct(DeviceAssignment.id)).filter(
                (Device.last_sync_at.is_(None)) | (Device.last_sync_at < cut)
            ),
            func.count(distinct(Sanction.resident_id)),
        )
        .select_from(Cell)
        .join(Floor, Floor.id == Cell.floor_id)
        .join(Line, Line.id == Floor.line_id)
        .join(Hub, Hub.id == Line.hub_id)
        .outerjoin(DeviceAssignment, open_a)
        .outerjoin(Device, Device.id == DeviceAssignment.device_id)
        .outerjoin(
            Sanction,
            and_(
                Sanction.resident_id == DeviceAssignment.resident_id,
                Sanction.status == "active",
                Sanction.ends_at > now,
            ),
        )
        .group_by(Hub.code, Line.code, Floor.level)
        .order_by(Hub.code, Line.code, Floor.level)
    ).all()
    hubs: dict[str, dict] = {}

    def add(into: dict, cells: int, occ: int, off: int, locked: int) -> None:
        into["cells"] += cells
        into["occupied"] += occ
        into["offline"] += off
        into["locked"] += locked

    def blank(**k) -> dict:
        return {**k, "cells": 0, "occupied": 0, "offline": 0, "locked": 0}

    for hub, line, level, cells, occ, off, locked in rows:
        h = hubs.setdefault(hub, blank(code=hub, lines={}))
        ln = h["lines"].setdefault(line, blank(code=line, floors=[]))
        floor_row = blank(level=level)
        add(floor_row, cells, occ, off, locked)
        ln["floors"].append(floor_row)
        add(ln, cells, occ, off, locked)
        add(h, cells, occ, off, locked)
    tree = [{**h, "lines": list(h["lines"].values())} for h in hubs.values()]
    total = blank()
    for h in tree:
        add(total, h["cells"], h["occupied"], h["offline"], h["locked"])
    return {"hubs": tree, "total": total}
