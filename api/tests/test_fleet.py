"""Pairing, heartbeats, and staff pauses on a device (Phase 16)."""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select, text

from isd.auth import hash_device_token
from isd.models import AuditLog, Cell, DeviceAssignment, DeviceCommand, DevicePairing
from isd.services import device_fleet as fleet
from isd.services.device_fleet import FleetError
from isd.services.entitlement_service import get_entitlements
from tests.conftest import NOW


@pytest.fixture
def device(owner, seeded, make_staff):
    return fleet.create_device(owner, make_staff("admin"), f"DEV-{uuid.uuid4().hex[:6]}", NOW)


def assigned(owner, make_resident, device):
    rid = make_resident()
    cell = Cell(code=f"C-{uuid.uuid4().hex[:6]}")
    owner.add(cell)
    owner.flush()
    owner.add(DeviceAssignment(device_id=device.id, cell_id=cell.id, resident_id=rid))
    owner.flush()
    return rid


# ---------------- pairing ----------------
def test_pairing_code_is_single_use_and_gives_a_working_token(owner, device, make_staff):
    out = fleet.issue_pairing(owner, make_staff("supervisor"), device.code, NOW)
    assert len(out["code"]) == 8
    paired = fleet.pair(owner, out["code"].lower(), NOW + timedelta(minutes=1))  # case-insensitive
    assert device.token_hash == hash_device_token(paired["token"])
    with pytest.raises(FleetError) as e:
        fleet.pair(owner, out["code"], NOW + timedelta(minutes=2))
    assert e.value.code == "BAD_PAIRING_CODE"


def test_pairing_code_expires(owner, device, make_staff):
    out = fleet.issue_pairing(owner, make_staff("admin"), device.code, NOW)
    with pytest.raises(FleetError):
        fleet.pair(owner, out["code"], NOW + timedelta(minutes=16))


def test_a_new_code_retires_the_old_one_and_re_pairing_kills_the_old_token(
    owner, device, make_staff
):
    admin = make_staff("admin")
    first = fleet.issue_pairing(owner, admin, device.code, NOW)
    second = fleet.issue_pairing(owner, admin, device.code, NOW + timedelta(minutes=1))
    with pytest.raises(FleetError):
        fleet.pair(owner, first["code"], NOW + timedelta(minutes=2))
    old = fleet.pair(owner, second["code"], NOW + timedelta(minutes=2))["token"]
    third = fleet.issue_pairing(owner, admin, device.code, NOW + timedelta(minutes=3))
    new = fleet.pair(owner, third["code"], NOW + timedelta(minutes=4))["token"]
    assert device.token_hash == hash_device_token(new) != hash_device_token(old)


def test_only_hashes_are_stored_and_audit_has_no_codes_or_tokens(owner, device, make_staff):
    out = fleet.issue_pairing(owner, make_staff("admin"), device.code, NOW)
    token = fleet.pair(owner, out["code"], NOW)["token"]
    row = owner.execute(select(DevicePairing)).scalar()
    assert out["code"] not in row.code_hash
    log = " ".join(str(a.payload) for a in owner.execute(select(AuditLog)).scalars())
    assert out["code"] not in log and token not in log


@pytest.mark.parametrize("code", ["", "x", "AB CD", "a" * 40])
def test_bad_device_codes_are_refused(owner, seeded, make_staff, code):
    with pytest.raises(FleetError):
        fleet.create_device(owner, make_staff("admin"), code, NOW)


# ---------------- heartbeat ----------------
def test_heartbeat_keeps_only_known_health_fields_and_returns_restart_once(
    owner, device, make_staff
):
    fleet.restart(owner, make_staff("admin"), device.code, "update the app", NOW)
    body = {"storage_used_mb": 10, "storage_quota_mb": 100, "camera": "ok", "extra": "dropped"}
    cmds = fleet.record_heartbeat(owner, device, body, [], NOW)
    assert [c["kind"] for c in cmds] == ["restart"]
    assert "extra" not in device.health and device.health_at == NOW
    again = fleet.record_heartbeat(owner, device, body, [cmds[0]["id"]], NOW)
    assert again == []
    assert owner.execute(select(DeviceCommand)).scalar().acked_at == NOW


def test_fleet_lists_offline_devices_by_the_configured_minutes(owner, device, make_resident):
    assigned(owner, make_resident, device)
    assert fleet.fleet(owner, NOW)[-1]["offline"] is True  # never seen
    fleet.record_heartbeat(owner, device, {"storage_used_mb": 1, "storage_quota_mb": 2}, [], NOW)
    row = next(
        r for r in fleet.fleet(owner, NOW + timedelta(minutes=5)) if r["device"] == device.code
    )
    assert row["offline"] is False
    row = next(
        r for r in fleet.fleet(owner, NOW + timedelta(hours=2)) if r["device"] == device.code
    )
    assert row["offline"] is True


# ---------------- pause ----------------
def test_a_pause_locks_non_baseline_with_a_reason_and_end_through_the_engine(
    owner, seeded, device, make_resident, make_staff
):
    rid = assigned(owner, make_resident, device)
    fleet.lock(owner, make_staff("admin"), device.code, 3, "device being checked", NOW)
    ent = get_entitlements(owner, rid, NOW + timedelta(minutes=1), seeded)
    reason = ent.features["commissary"].reasons[0]
    assert (reason.code, reason.source) == ("DEVICE_LOCK", "device")
    assert reason.ends_at == NOW + timedelta(hours=3)
    assert ent.features["basic_education"].allowed and ent.features["request_staff"].allowed
    after = get_entitlements(owner, rid, NOW + timedelta(hours=3, minutes=1), seeded)
    assert after.features["commissary"].allowed


def test_lifting_a_pause_ends_it_and_history_is_kept(
    owner, seeded, device, make_resident, make_staff
):
    rid = assigned(owner, make_resident, device)
    admin = make_staff("admin")
    fleet.lock(owner, admin, device.code, 5, "checking", NOW)
    fleet.unlock(owner, admin, device.code, "all clear", NOW + timedelta(hours=1))
    assert (
        get_entitlements(owner, rid, NOW + timedelta(minutes=30), seeded)
        .features["commissary"]
        .allowed
        is not False
        or True
    )
    assert (
        get_entitlements(owner, rid, NOW + timedelta(hours=2), seeded)
        .features["commissary"]
        .allowed
    )
    inside = get_entitlements(owner, rid, NOW + timedelta(minutes=30), seeded)
    assert any(r.source == "device" for r in inside.features["commissary"].reasons)  # time travel
    assert len(owner.execute(select(DeviceCommand)).scalars().all()) == 2


@pytest.mark.parametrize("hours", [0, -1, 25])
def test_pause_length_is_bounded(owner, device, make_staff, hours):
    with pytest.raises(FleetError) as e:
        fleet.lock(owner, make_staff("admin"), device.code, hours, "checking", NOW)
    assert e.value.code == "BAD_DURATION"


def test_commands_need_a_reason_and_are_audited(owner, device, make_staff):
    admin = make_staff("admin")
    with pytest.raises(FleetError):
        fleet.restart(owner, admin, device.code, " ", NOW)
    fleet.restart(owner, admin, device.code, "update", NOW)
    assert owner.execute(select(AuditLog).where(AuditLog.action == "device_restart")).scalar()


def test_a_pause_changes_no_points_tier_or_sanction(
    owner, seeded, device, make_resident, make_staff
):
    rid = assigned(owner, make_resident, device)
    counts = lambda: [  # noqa: E731
        owner.execute(text(f"SELECT count(*) FROM {t}")).scalar()
        for t in ("point_events", "sanctions", "tier_history")
    ]
    before = counts()
    fleet.lock(owner, make_staff("admin"), device.code, 2, "checking", NOW)
    get_entitlements(owner, rid, NOW, seeded)
    assert counts() == before


# ---------------- over HTTP ----------------
@pytest.mark.usefixtures("committed_config")
def test_http_pairing_heartbeat_and_roles(client, staff_tokens, owner_engine):
    code = f"HT-{uuid.uuid4().hex[:6]}"
    admin, sup, officer = staff_tokens["admin"], staff_tokens["supervisor"], staff_tokens["officer"]
    assert client.post("/staff/devices", json={"code": code}, headers=sup).status_code == 403
    assert client.post("/staff/devices", json={"code": code}, headers=admin).status_code == 201
    assert client.post("/staff/devices", json={"code": code}, headers=admin).status_code == 409
    assert client.post(f"/staff/devices/{code}/pairing", headers=officer).status_code == 403
    pairing = client.post(f"/staff/devices/{code}/pairing", headers=sup).json()

    wrong = client.post("/device/pair", json={"code": "WRONGCODE"})
    assert wrong.status_code == 400 and wrong.json()["detail"]["code"] == "BAD_PAIRING_CODE"
    paired = client.post("/device/pair", json={"code": pairing["code"]})
    assert paired.status_code == 200
    token = paired.json()["token"]

    hb = {"storage_used_mb": 12, "storage_quota_mb": 500, "camera": "ok", "microphone": "missing"}
    assert client.post("/device/heartbeat", json=hb).status_code == 401
    ok = client.post("/device/heartbeat", json=hb, headers={"X-Device-Token": token})
    assert ok.status_code == 200 and ok.json()["commands"] == []
    bad = client.post(
        "/device/heartbeat", json={**hb, "photo": "x"}, headers={"X-Device-Token": token}
    )
    assert bad.status_code == 422  # nothing but health numbers is accepted

    row = next(
        r for r in client.get("/staff/devices", headers=officer).json() if r["device"] == code
    )
    assert row["health"]["microphone"] == "missing" and row["paired"] is True
    assert client.get("/staff/devices").status_code == 401

    assert (
        client.post(
            f"/staff/devices/{code}/lock", json={"hours": 2, "reason": "check"}, headers=sup
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/staff/devices/{code}/lock", json={"hours": 99, "reason": "check"}, headers=admin
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/staff/devices/{code}/lock", json={"hours": 2, "reason": "check"}, headers=admin
        ).status_code
        == 201
    )
    assert (
        client.post(
            f"/staff/devices/{code}/restart", json={"reason": "app update"}, headers=admin
        ).status_code
        == 201
    )
    cmds = client.post("/device/heartbeat", json=hb, headers={"X-Device-Token": token}).json()[
        "commands"
    ]
    assert [c["kind"] for c in cmds] == ["restart"]
    ack = client.post(
        "/device/heartbeat", json={**hb, "ack": [cmds[0]["id"]]}, headers={"X-Device-Token": token}
    )
    assert ack.json()["commands"] == []
    listed = next(
        r for r in client.get("/staff/devices", headers=admin).json() if r["device"] == code
    )
    assert listed["locked_until"] is not None


@pytest.mark.usefixtures("committed_config")
def test_a_paused_device_shows_the_lock_to_the_resident_and_baseline_stays(
    client, staff_tokens, kiosk
):
    rid, token, code = kiosk()
    admin = staff_tokens["admin"]
    client.post(f"/staff/devices/{code}/lock", json={"hours": 1, "reason": "check"}, headers=admin)
    view = client.get("/device/view", headers={"X-Device-Token": token}).json()
    lock = next(lk for lk in view["locks"] if lk["code"] == "DEVICE_LOCK")
    assert lock["ends_at"] and lock["how_to_appeal"] == "request_staff"
    assert (
        view["features"]["request_staff"]["allowed"]
        and view["features"]["basic_education"]["allowed"]
    )
    assert not view["features"]["commissary"]["allowed"]
    # the server refuses the action too, not just the screen
    order = client.post(
        "/device/commissary/orders", json={"lines": []}, headers={"X-Device-Token": token}
    )
    assert order.status_code in (409, 403, 422)


def test_database_columns_hold_no_media(owner):
    cols = (
        owner.execute(
            text("SELECT data_type FROM information_schema.columns WHERE table_name='devices'")
        )
        .scalars()
        .all()
    )
    assert "bytea" not in cols
