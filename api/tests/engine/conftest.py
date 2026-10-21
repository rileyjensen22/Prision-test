from datetime import UTC, datetime

import pytest

from isd.config_loader import load_config
from isd.engine.config import EngineConfig

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


@pytest.fixture(scope="session")
def cfg() -> EngineConfig:
    return EngineConfig.from_sections(load_config())
