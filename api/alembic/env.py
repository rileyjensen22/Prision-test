from sqlalchemy import create_engine

from alembic import context
from isd import settings
from isd.models import Base

target_metadata = Base.metadata


def _url() -> str:
    return context.config.attributes.get("url") or settings.MIGRATION_DATABASE_URL


def run_migrations_online() -> None:
    engine = create_engine(_url())
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
