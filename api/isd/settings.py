"""Runtime settings from the environment. Defaults are development-only; `validate_for_env`
refuses a production start that still uses them."""

import os

ENV = os.environ.get("ISD_ENV", "dev")  # dev | production
DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg://isd_app:isd_app_dev_only@localhost:5432/isd"
)
MIGRATION_DATABASE_URL = os.environ.get(
    "MIGRATION_DATABASE_URL", "postgresql+psycopg://isd:isd_dev_only@localhost:5432/isd"
)
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-secret-change-me")
PUBLIC_LOG_SALT = os.environ.get("PUBLIC_LOG_SALT", "dev-only-public-log-salt-change-me")
RESEARCH_SALT = os.environ.get("RESEARCH_SALT", "dev-only-research-salt-change-me")
DB_POOL_SIZE = int(os.environ.get("DB_POOL_SIZE", "20"))  # per API process
DB_POOL_OVERFLOW = int(os.environ.get("DB_POOL_OVERFLOW", "20"))
TOKEN_TTL_SECONDS = int(os.environ.get("TOKEN_TTL_SECONDS", "1800"))  # staff idle timeout
MAX_BODY_BYTES = int(os.environ.get("MAX_BODY_BYTES", str(1024 * 1024)))
SSO_MOCK_ENABLED = (
    os.environ.get("SSO_MOCK_ENABLED", "true" if ENV != "production" else "false") == "true"
)
RATE_LIMIT_ENABLED = os.environ.get("RATE_LIMIT_ENABLED", "true") == "true"


def validate_for_env(
    env: str | None = None,
    *,
    secret_key: str | None = None,
    salt: str | None = None,
    database_url: str | None = None,
    migration_url: str | None = None,
    sso_mock: bool | None = None,
    research_salt: str | None = None,
) -> list[str]:
    """Returns the problems that make these settings unsafe for production (empty list = fine).

    Arguments exist so tests can check combinations; with none given it checks the live settings.
    """
    if (env or ENV) != "production":
        return []
    sk = SECRET_KEY if secret_key is None else secret_key
    sl = PUBLIC_LOG_SALT if salt is None else salt
    rs = RESEARCH_SALT if research_salt is None else research_salt
    db = DATABASE_URL if database_url is None else database_url
    mg = MIGRATION_DATABASE_URL if migration_url is None else migration_url
    sso = SSO_MOCK_ENABLED if sso_mock is None else sso_mock
    problems = []
    if sk.startswith("dev-only") or len(sk) < 32:
        problems.append("SECRET_KEY must be set to a random value of at least 32 characters")
    if sl.startswith("dev-only") or len(sl) < 16:
        problems.append("PUBLIC_LOG_SALT must be set to a random value")
    if rs.startswith("dev-only") or len(rs) < 16:
        problems.append(
            "RESEARCH_SALT must be set to a random value, different from PUBLIC_LOG_SALT"
        )
    if rs == sl:
        problems.append("RESEARCH_SALT must differ from PUBLIC_LOG_SALT")
    if "_dev_only" in db or "_dev_only" in mg:
        problems.append("database URLs still contain the development passwords")
    if db == mg:
        problems.append(
            "the app and migration database users must be different (app must not own the schema)"
        )
    if sso:
        problems.append("the mock SSO must be disabled in production")
    return problems
