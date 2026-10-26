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
# Where rate-limit counts live: 'postgres' is shared by every API process; 'memory' is per process.
RATE_LIMIT_STORE = os.environ.get(
    "RATE_LIMIT_STORE", "postgres" if ENV == "production" else "memory"
)
# Staff must have an authenticator app (TOTP) set up. On by default in production, off in
# development so the demo and tests can sign in with a password alone.
STAFF_MFA_REQUIRED = (
    os.environ.get("STAFF_MFA_REQUIRED", "true" if ENV == "production" else "false") == "true"
)
# Encryption at rest (isd/crypto.py). KEYS is "id:base64key,id2:base64key2" (32 random bytes each);
# the active key encrypts new values, every listed key can still decrypt, which is how rotation
# works. BLIND_INDEX_KEY makes a searchable keyed hash of contact numbers and never changes.
ENCRYPTION_KEYS = os.environ.get("ENCRYPTION_KEYS", "")
ENCRYPTION_ACTIVE_KEY_ID = os.environ.get("ENCRYPTION_ACTIVE_KEY_ID", "")
BLIND_INDEX_KEY = os.environ.get("BLIND_INDEX_KEY", "dev-only-blind-index-key-change-me")


def validate_for_env(
    env: str | None = None,
    *,
    secret_key: str | None = None,
    salt: str | None = None,
    database_url: str | None = None,
    migration_url: str | None = None,
    sso_mock: bool | None = None,
    research_salt: str | None = None,
    encryption_keys: str | None = None,
    blind_index_key: str | None = None,
    mfa_required: bool | None = None,
    rate_limit_store: str | None = None,
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
    keys = ENCRYPTION_KEYS if encryption_keys is None else encryption_keys
    if not keys.strip():
        problems.append("ENCRYPTION_KEYS must be set (id:base64key, 32 random bytes per key)")
    bk = BLIND_INDEX_KEY if blind_index_key is None else blind_index_key
    if bk.startswith("dev-only") or len(bk) < 32:
        problems.append("BLIND_INDEX_KEY must be set to a random value of at least 32 characters")
    if not (STAFF_MFA_REQUIRED if mfa_required is None else mfa_required):
        problems.append("STAFF_MFA_REQUIRED must be true in production")
    if (RATE_LIMIT_STORE if rate_limit_store is None else rate_limit_store) != "postgres":
        problems.append("RATE_LIMIT_STORE must be postgres in production (shared by every process)")
    return problems
