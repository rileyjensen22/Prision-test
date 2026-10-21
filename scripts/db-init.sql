-- Dev/CI cluster bootstrap (run as a Postgres superuser). Idempotent.
-- isd     = schema owner, used only for migrations/seed.
-- isd_app = runtime role used by the API; migrations revoke UPDATE/DELETE on audit tables from it.
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'isd') THEN
    CREATE ROLE isd LOGIN PASSWORD 'isd_dev_only' CREATEDB;
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'isd_app') THEN
    CREATE ROLE isd_app LOGIN PASSWORD 'isd_app_dev_only';
  END IF;
END $$;
SELECT 'CREATE DATABASE isd OWNER isd'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'isd')\gexec
