"""Load and validate seed YAML config from /config."""

from pathlib import Path

import yaml

from isd.engine.config import (
    validate_commissary,
    validate_courses,
    validate_offenses,
    validate_reading,
    validate_rec,
    validate_sanctions,
    validate_welfare,
)
from isd.jobs_config import validate_jobs  # noqa: E402

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"
CONFIG_FILES = (
    "tiers",
    "points",
    "sanctions",
    "offenses",
    "compliance",
    "commissary",
    "courses",
    "welfare",
    "jobs",
    "rec",
    "reading",
)


def load_config(config_dir: Path = CONFIG_DIR) -> dict[str, dict]:
    config = {}
    for name in CONFIG_FILES:
        with (config_dir / f"{name}.yaml").open() as f:
            config[name] = yaml.safe_load(f)
    validate_config(config)
    return config


def validate_config(config: dict[str, dict]) -> None:
    for name, payload in config.items():
        validate_section(name, payload)


def validate_section(name: str, payload: dict) -> None:
    if name == "tiers":
        _validate_tiers(payload)
    elif name == "sanctions":
        validate_sanctions(payload)
    elif name == "offenses":
        validate_offenses(payload)
    elif name == "commissary":
        validate_commissary(payload)
    elif name == "courses":
        validate_courses(payload)
    elif name == "welfare":
        validate_welfare(payload)
    elif name == "jobs":
        validate_jobs(payload)
    elif name == "rec":
        validate_rec(payload)
    elif name == "reading":
        validate_reading(payload)
    elif name not in CONFIG_FILES:
        raise ValueError(f"unknown config section: {name}")


def _validate_tiers(tiers: dict) -> None:
    required = {"promotion_thresholds", "demotion_hysteresis", "tiers"}
    if missing := required - set(tiers):
        raise ValueError(f"tiers config missing keys: {sorted(missing)}")
    thresholds = tiers["promotion_thresholds"]
    if len(thresholds) != 10 or thresholds[0] != 0 or thresholds != sorted(set(thresholds)):
        raise ValueError("promotion_thresholds must be 10 strictly increasing values from 0")
    if sorted(int(k) for k in tiers["tiers"]) != list(range(1, 11)):
        raise ValueError("tiers must define T1..T10")
    if not 0 <= tiers["demotion_hysteresis"] < 1:
        raise ValueError("demotion_hysteresis must be in [0, 1)")
