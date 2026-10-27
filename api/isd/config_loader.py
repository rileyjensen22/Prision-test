"""Load and validate seed YAML config from /config."""

from pathlib import Path

import yaml

from isd.courses_loader import COURSES_DIR, assemble, load_courses
from isd.engine.config import (
    validate_chess,
    validate_commissary,
    validate_courses,
    validate_offenses,
    validate_reading,
    validate_rec,
    validate_sanctions,
    validate_welfare,
)
from isd.engine.monitoring import validate_monitoring
from isd.engine.reentry import validate_reentry
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
    "monitoring",
    "reentry",
    "chess",
)


def load_config(config_dir: Path = CONFIG_DIR, courses_dir: Path | None = None) -> dict[str, dict]:
    config = {}
    for name in CONFIG_FILES:
        with (config_dir / f"{name}.yaml").open() as f:
            config[name] = yaml.safe_load(f)
    # The course list comes from the folders under content/courses, not from the yaml.
    kinds = set(config["points"]["events"])
    config["courses"] = assemble(config["courses"], load_courses(courses_dir or COURSES_DIR), kinds)
    validate_config(config)
    return config


def validate_config(config: dict[str, dict]) -> None:
    for name, payload in config.items():
        validate_section(name, payload)
    if "reentry" in config and "courses" in config:  # the reentry courses must exist
        codes = {c["code"] for c in config["courses"]["courses"]}
        validate_reentry(config["reentry"], codes)


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
    elif name == "monitoring":
        validate_monitoring(payload)
    elif name == "reentry":
        validate_reentry(payload)
    elif name == "chess":
        validate_chess(payload)
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
