import os

# Dev defaults only; real deployments set these via environment (see .env.example).
DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg://isd_app:isd_app_dev_only@localhost:5432/isd"
)
MIGRATION_DATABASE_URL = os.environ.get(
    "MIGRATION_DATABASE_URL", "postgresql+psycopg://isd:isd_dev_only@localhost:5432/isd"
)
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-secret-change-me")
TOKEN_TTL_SECONDS = int(os.environ.get("TOKEN_TTL_SECONDS", "28800"))
PUBLIC_LOG_SALT = os.environ.get("PUBLIC_LOG_SALT", "dev-only-public-log-salt-change-me")
