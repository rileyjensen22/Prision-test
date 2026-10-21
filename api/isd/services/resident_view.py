"""Build the ResidentView payload. Used by the kiosk now, by staff sandbox/mirror in Phase 6."""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from isd.engine.calls import minutes_used
from isd.engine.features import BASELINE_FEATURES
from isd.engine.sandbox import SandboxOverrides, apply_to_settings
from isd.models import Appeal, Resident
from isd.schemas import (
    AllowanceOut,
    FeatureOut,
    LockOut,
    ReasonOut,
    ResidentSettings,
    ResidentView,
    TierOut,
    UiConfig,
)
from isd.services.config_store import get_current
from isd.services.entitlement_service import get_entitlements, load_engine_config
from isd.services.points import total_points
from isd.services.usage import call_seconds_today, spent_cents_this_week

_ALLOWANCES = [  # feature, limit key, period, unit
    ("calls", "minutes_per_day", "day", "minutes"),
    ("texting", "messages_per_day", "day", "messages"),
    ("video", "minutes_per_week", "week", "minutes"),
    ("commissary", "dollars_per_week", "week", "dollars"),
    ("outdoor_rec", "minutes_per_day", "day", "minutes"),
]


def build_resident_view(
    session: Session,
    resident_id: int,
    at_time: datetime,
    simulation: bool = False,
    overrides: SandboxOverrides | None = None,
) -> ResidentView:
    cfg = load_engine_config(session)
    resident = session.get(Resident, resident_id)
    ent = get_entitlements(session, resident_id, at_time, cfg, overrides)
    compliance = get_current(session, "compliance").payload
    ttl = timedelta(minutes=int(compliance["entitlement_snapshot_ttl_minutes"]))
    valid_until = min(filter(None, [ent.next_change_at, at_time + ttl]))

    features = {
        name: FeatureOut(
            allowed=fe.allowed,
            baseline=name in BASELINE_FEATURES,
            limits=fe.limits,
            reasons=[
                ReasonOut(
                    **{
                        k: getattr(r, k)
                        for k in ("code", "source", "how_to_appeal", "ends_at", "detail", "params")
                    },
                    sanction_id=r.ref_id,
                )
                for r in fe.reasons
            ],
        )
        for name, fe in sorted(ent.features.items())
    }
    open_appeals = set(
        session.execute(select(Appeal.sanction_id).where(Appeal.status == "open")).scalars()
    )
    used = {
        "calls": minutes_used(call_seconds_today(session, resident_id, at_time)),
        "commissary": spent_cents_this_week(session, resident_id, at_time) / 100,
    }
    return ResidentView(
        resident_code=resident.code,
        settings=ResidentSettings(**_settings(resident, overrides)),
        tier=_tier(session, resident_id, ent, cfg, at_time, overrides),
        features=features,
        allowances=[
            AllowanceOut(
                feature=f, period=p, unit=u, limit=features[f].limits[k], used=used.get(f, 0)
            )
            for f, k, p, u in _ALLOWANCES
            if features[f].allowed and k in features[f].limits
        ],
        locks=_group_locks(features, open_appeals),
        generated_at=at_time,
        valid_until=valid_until,
        simulation=simulation,
        ui=UiConfig(
            inactivity_return_home_seconds=int(compliance["inactivity_return_home_seconds"])
        ),
    )


def _settings(resident: Resident, overrides: SandboxOverrides | None) -> dict:
    base = {
        "language": resident.language,
        "text_size": resident.text_size,
        "reading_level": resident.reading_level,
        "captions": resident.captions,
    }
    return apply_to_settings(base, overrides) if overrides else base


def _tier(session, resident_id, ent, cfg, at_time, overrides=None) -> TierOut:
    points = total_points(session, resident_id, at_time)
    if overrides is not None and overrides.tier is not None:
        points = cfg.thresholds[overrides.tier - 1]  # show the points a tier-N resident would have
    earned = ent.earned_tier
    nxt = earned + 1 if earned < 10 else None
    return TierOut(
        earned=earned,
        ceiling=ent.ceiling_tier,
        effective=ent.effective_tier,
        points=points,
        next_tier=nxt,
        points_to_next=max(0, cfg.thresholds[earned] - points) if nxt else None,
        # True whenever the resident has earned everything their ceiling allows
        capped_by_ceiling=ent.ceiling_tier < 10 and ent.earned_tier >= ent.ceiling_tier,
    )


def _group_locks(features: dict[str, FeatureOut], open_appeals: set[int]) -> list[LockOut]:
    """Group per-feature reasons into one entry per underlying lock (sanction / offense / tier)."""
    locks: dict[str, LockOut] = {}
    for name, fe in features.items():
        for r in fe.reasons:
            if r.source == "tier":
                continue  # "not unlocked yet" is shown on the tile, not as a restriction
            key = (
                f"{r.source}:{r.sanction_id or r.code}:{r.detail if r.source == 'offense' else ''}"
            )
            if key not in locks:
                locks[key] = LockOut(
                    key=key,
                    code=r.code,
                    source=r.source,
                    features=[],
                    ends_at=r.ends_at,
                    detail=r.detail,
                    params=r.params,
                    how_to_appeal=r.how_to_appeal,
                    sanction_id=r.sanction_id,
                    appeal_open=r.sanction_id in open_appeals,
                )
            locks[key].features.append(name)
    return sorted(locks.values(), key=lambda lk: (lk.ends_at is None, lk.ends_at, lk.key))
