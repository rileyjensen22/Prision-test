from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from isd import settings

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_POOL_OVERFLOW,
)
# Used only by the shared rate limiter: one autocommit statement per check, on its own connections.
limiter_engine = create_engine(
    settings.DATABASE_URL,
    pool_size=settings.LIMITER_POOL_SIZE,
    max_overflow=settings.LIMITER_POOL_SIZE,
    isolation_level="AUTOCOMMIT",
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    with SessionLocal() as session:
        session.info["config_cache"] = {}  # per request; see services/config_store.py
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


def get_readonly_db() -> Iterator[Session]:
    """A session whose transaction the database itself refuses to write in, and never commits.

    Used by sandbox ("view as") so that "no writes, no side effects" is enforced by Postgres,
    not just by careful code.
    """
    with SessionLocal() as session:
        session.info["config_cache"] = {}
        session.execute(text("SET TRANSACTION READ ONLY"))
        try:
            yield session
        finally:
            session.rollback()
