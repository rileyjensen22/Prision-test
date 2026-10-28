"""Synthetic residents and devices for a whole facility, in bulk. Used by `make seed-full` and the
load test. Synthetic data only (invariant 11): made-up codes, no names."""

import random
from collections.abc import Callable
from datetime import datetime

from sqlalchemy.orm import Session

from isd.auth import hash_device_token
from isd.models import Device, DeviceAssignment, Resident
from isd.services import facility_model, points
from isd.services.audit import SYSTEM


def populate(
    session: Session,
    scale: dict,
    *,
    occupancy: float = 0.9,
    now: datetime,
    token_for: Callable[[str], str],
    seed: int = 1,
    with_points: float = 0.1,
) -> dict[str, str]:
    """Builds the facility at `scale`, then puts a resident and a device in `occupancy` of the
    cells (spread across every line and floor). Returns {device code: token}."""
    rng = random.Random(seed)
    cells = facility_model.build(session, scale)
    occupied = [c for c in cells if rng.random() < occupancy]
    residents, devices, tokens = [], [], {}
    for i, cell in enumerate(occupied):
        residents.append(
            Resident(
                code=f"FAC-{i + 1:05d}",
                display_name=f"Synthetic Resident {i + 1}",
                language=rng.choice(["en", "es"]),
                prior_returns=rng.choice([0, 0, 0, 1, 2, 4]),
                prior_returns_source="synthetic seed",
            )
        )
        token = token_for(cell.code)
        tokens[f"DEV-{cell.code}"] = token
        devices.append(
            Device(code=f"DEV-{cell.code}", token_hash=hash_device_token(token), last_sync_at=now)
        )
    session.add_all([*residents, *devices])
    session.flush()
    session.add_all(
        DeviceAssignment(device_id=d.id, cell_id=c.id, resident_id=r.id, assigned_at=now)
        for r, d, c in zip(residents, devices, occupied, strict=True)
    )
    session.flush()
    for r in residents:  # a spread of tiers for a realistic dashboard
        if rng.random() < with_points:
            points.record_points(
                session,
                SYSTEM,
                r.id,
                "seed_adjustment",
                rng.choice([60, 120, 300, 520, 800]),
                "system",
                now,
            )
            points.evaluate_tier(session, r.id, now)
    return tokens
