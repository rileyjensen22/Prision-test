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
