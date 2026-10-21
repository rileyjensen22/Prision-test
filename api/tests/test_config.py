import pytest

from isd.config_loader import load_config, validate_config


def test_seed_config_loads_and_matches_spec():
    cfg = load_config()
    expected = [0, 100, 250, 450, 700, 1000, 1400, 1900, 2500, 3200]
    assert cfg["tiers"]["promotion_thresholds"] == expected
    assert cfg["compliance"]["public_log_enabled"] is False
    assert set(cfg["sanctions"]["infractions"]) == {
        "DISRUPT",
        "CELL_MESS",
        "STAFF_DISRESPECT",
        "CAM_BLOCK",
        "DEVICE_TAMPER",
        "DEVICE_DAMAGE",
    }


def test_invalid_thresholds_rejected():
    cfg = load_config()
    cfg["tiers"]["promotion_thresholds"] = [0, 100, 50, 450, 700, 1000, 1400, 1900, 2500, 3200]
    with pytest.raises(ValueError):
        validate_config(cfg)
