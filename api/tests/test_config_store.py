import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from isd.config_loader import load_config
from isd.services.audit import Actor, verify_chain
from isd.services.config_store import get_current, list_versions, set_config

ADMIN = Actor(None, "admin")


def test_config_changes_are_versioned_and_audited(owner):
    tiers = load_config()["tiers"]
    v1 = set_config(owner, ADMIN, "tiers", tiers, "seed for test")
    tiers2 = {**tiers, "demotion_hysteresis": 0.2}
    v2 = set_config(owner, ADMIN, "tiers", tiers2, "tune hysteresis")
    assert v2.version == v1.version + 1
    assert get_current(owner, "tiers").payload["demotion_hysteresis"] == 0.2
    assert len(list_versions(owner, "tiers")) >= 2
    assert verify_chain(owner).ok


def test_reason_required_and_validation(owner):
    with pytest.raises(ValueError):
        set_config(owner, ADMIN, "tiers", {}, "  ")
    bad = {**load_config()["tiers"], "promotion_thresholds": [0, 5, 3]}
    with pytest.raises(ValueError):
        set_config(owner, ADMIN, "tiers", bad, "bad thresholds")
    with pytest.raises(ValueError):
        set_config(owner, ADMIN, "nonsense", {}, "unknown section")


def test_config_history_is_immutable(owner_engine):
    from sqlalchemy.orm import Session

    with Session(owner_engine) as s, s.begin():
        set_config(s, ADMIN, "points", load_config()["points"], "immutability test")
    with owner_engine.connect() as c, pytest.raises(DBAPIError, match="append-only"):
        c.execute(text("UPDATE config_versions SET reason = 'edited'"))


def test_config_api_put_requires_admin_and_logs(client, staff_tokens):
    payload = load_config()["tiers"]
    body = {"payload": payload, "reason": "api edit"}
    assert (
        client.put("/config/tiers", json=body, headers=staff_tokens["officer"]).status_code == 403
    )
    r = client.put("/config/tiers", json=body, headers=staff_tokens["admin"])
    assert r.status_code == 200
    entries = client.get("/audit?limit=500", headers=staff_tokens["auditor"]).json()
    assert any(e["action"] == "config_change" and e["target_id"] == "tiers" for e in entries)
    assert client.get("/audit/verify", headers=staff_tokens["auditor"]).json()["ok"]
    bad = client.put(
        "/config/tiers", json={"payload": {}, "reason": "x"}, headers=staff_tokens["admin"]
    )
    assert bad.status_code in (422, 500)
