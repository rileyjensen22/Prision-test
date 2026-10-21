"""Test DB: a fresh `isd_test` database migrated with Alembic; roles come from db-init.sql."""

import os

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from alembic import command
from isd import settings

TEST_DB = "isd_test"
OWNER_URL = make_url(settings.MIGRATION_DATABASE_URL).set(database=TEST_DB)
APP_URL = make_url(settings.DATABASE_URL).set(database=TEST_DB)


@pytest.fixture(scope="session")
def _database():
    admin = create_engine(make_url(settings.MIGRATION_DATABASE_URL), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as c:
            c.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)"))
            c.execute(text(f"CREATE DATABASE {TEST_DB}"))
    except Exception as exc:  # noqa: BLE001
        pytest.fail(
            f"Postgres not reachable/initialised ({exc}). Run `make db-local` first.",
            pytrace=False,
        )
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(os.path.dirname(__file__), "..", "alembic"))
    cfg.attributes["url"] = OWNER_URL.render_as_string(hide_password=False)
    command.upgrade(cfg, "head")
    yield
    admin.dispose()


@pytest.fixture(scope="session")
def owner_engine(_database):
    return create_engine(OWNER_URL)


@pytest.fixture(scope="session")
def app_engine(_database):
    return create_engine(APP_URL)


@pytest.fixture
def owner(owner_engine):
    with Session(owner_engine) as s:
        yield s
        s.rollback()


@pytest.fixture
def app_session(app_engine):
    with Session(app_engine) as s:
        yield s
        s.rollback()


@pytest.fixture(scope="session")
def client(app_engine):
    from isd import db
    from isd.main import app

    db.SessionLocal.configure(bind=app_engine)
    return TestClient(app)


@pytest.fixture(scope="session")
def staff_tokens(owner_engine, client):
    """One staff account per role; returns {role: auth headers}."""
    from isd.auth import hash_password, make_token
    from isd.models import ROLES, Staff

    headers = {}
    with Session(owner_engine) as s, s.begin():
        for role in ROLES:
            st = Staff(username=f"test_{role}", role=role, password_hash=hash_password("pw-test"))
            s.add(st)
            s.flush()
            headers[role] = {"Authorization": f"Bearer {make_token(st.id)}"}
    return headers


# ---- helpers for service-level tests (all run inside the rolled-back `owner` session) ----
import uuid  # noqa: E402
from datetime import UTC, datetime  # noqa: E402

NOW = datetime(2026, 3, 2, 9, 0, tzinfo=UTC)


@pytest.fixture
def seeded(owner):
    """Seed config into the test transaction; returns the loaded EngineConfig."""
    from isd.config_loader import load_config
    from isd.services.audit import SYSTEM
    from isd.services.config_store import set_config
    from isd.services.entitlement_service import load_engine_config

    for name, payload in load_config().items():
        set_config(owner, SYSTEM, name, payload, "test seed")
    return load_engine_config(owner)


@pytest.fixture
def make_staff(owner):
    from isd.models import Staff
    from isd.services.audit import Actor

    def _make(role: str) -> Actor:
        st = Staff(username=f"{role}_{uuid.uuid4().hex[:8]}", role=role, password_hash="x")
        owner.add(st)
        owner.flush()
        return Actor(st.id, role)

    return _make


@pytest.fixture
def make_resident(owner):
    from isd.models import Resident

    def _make(prior_returns: int = 0) -> int:
        r = Resident(
            code=f"RES-{uuid.uuid4().hex[:8]}",
            display_name="Synthetic",
            prior_returns=prior_returns,
        )
        owner.add(r)
        owner.flush()
        return r.id

    return _make
