import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from isd.auth import hash_device_token
from isd.models import AuditLog, Device

pytestmark = pytest.mark.usefixtures("committed_config")


def test_rotating_a_device_token_replaces_it_at_once(client, kiosk, staff_tokens, owner_engine):
    rid, old, code = kiosk()
    assert client.get("/device/view", headers={"X-Device-Token": old}).status_code == 200
    assert (
        client.post(f"/staff/devices/{code}/token", headers=staff_tokens["supervisor"]).status_code
        == 403
    )
    assert client.post(f"/staff/devices/{code}/token").status_code == 401
    r = client.post(f"/staff/devices/{code}/token", headers=staff_tokens["admin"])
    assert r.status_code == 200
    new = r.json()["token"]
    assert len(new) >= 40 and r.json()["kiosk_address_fragment"] == f"#device={new}"
    assert client.get("/device/view", headers={"X-Device-Token": old}).status_code == 401
    assert client.get("/device/view", headers={"X-Device-Token": new}).status_code == 200
    assert (
        new != old
        and client.post("/staff/devices/NOPE/token", headers=staff_tokens["admin"]).status_code
        == 404
    )

    with Session(owner_engine) as s:
        assert s.execute(
            select(Device.token_hash).where(Device.code == code)
        ).scalar() == hash_device_token(new)
        entries = (
            s.execute(select(AuditLog).where(AuditLog.action == "device_token_rotated"))
            .scalars()
            .all()
        )
        assert entries and all(
            new not in str(e.payload) and old not in str(e.payload) for e in entries
        )
        assert not s.execute(
            select(Device).where(Device.token_hash == new)
        ).first()  # only the hash is stored
