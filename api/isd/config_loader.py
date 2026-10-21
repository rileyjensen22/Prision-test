"""Load and validate seed YAML config from /config."""

from pathlib import Path

import yaml

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"
CONFIG_FILES = ("tiers", "points", "sanctions", "offenses", "compliance")


def load_config(config_dir: Path = CONFIG_DIR) -> dict[str, dict]:
    config = {}
    for name in CONFIG_FILES:
        with (config_dir / f"{name}.yaml").open() as f:
            config[name] = yaml.safe_load(f)
    validate_config(config)
    return config


def validate_config(config: dict[str, dict]) -> None:
    tiers = config["tiers"]
    thresholds = tiers["promotion_thresholds"]
    if len(thresholds) != 10 or thresholds[0] != 0 or thresholds != sorted(set(thresholds)):
        raise ValueError("promotion_thresholds must be 10 strictly increasing values from 0")
    if sorted(tiers["tiers"]) != list(range(1, 11)):
        raise ValueError("tiers must define T1..T10")
    if not 0 <= tiers["demotion_hysteresis"] < 1:
        raise ValueError("demotion_hysteresis must be in [0, 1)")
