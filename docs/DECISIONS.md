# Decisions

## Phase 0

- **Seed writes JSON, not Postgres (yet).** The data model arrives in Phase 1; `make seed` produces `var/seed.json` from `/config` plus synthetic people. Rejected: stubbing tables early (would be thrown away).
- **Config is YAML in `/config`, validated by `isd.config_loader`.** Phase 1 moves it into versioned DB tables (invariant 9); YAML stays as the seed source.
- **Python `>=3.12`.** Dev sandbox has 3.13; CI and Docker use 3.12.
- **Makefile uses a local `.venv`** so `make test` needs no Docker/Postgres in Phase 0.
- **Playwright `CHROMIUM_PATH` env override** for sandboxes with a preinstalled browser; CI downloads its own.
- **Stub scripts** for `simulate-week` and `export-public-log` exist so every Makefile target runs; real logic lands in Phases 7-8.
- **Tailwind v3** chosen over v4 for stable PostCSS config.

## Phase 1

- **Two DB roles.** `isd` owns the schema (migrations/seed only); `isd_app` is the runtime role. Migration 0001 revokes UPDATE/DELETE/TRUNCATE on `audit_log` and `config_versions` from `isd_app`. Rejected: single role (grants alone would not hold against the app's own credentials).
- **Trigger as second layer.** `forbid_mutation()` BEFORE UPDATE/DELETE/TRUNCATE triggers fire for every role, including the owner. Known limit: a Postgres superuser can disable triggers or set `session_replication_role=replica`; the hash chain is the detection control for that case (`GET /audit/verify`).
- **Hash chain computed in the app, under `pg_advisory_xact_lock`.** Gapless `seq` (not a DB sequence, which can skip) so deletions show as gaps. Each hash covers `prev_hash` + canonical JSON of all fields. Payloads must avoid floats. Rejected: DB-side hashing (needs pgcrypto, harder to test/version).
- **Corrections, not edits.** `POST /audit/corrections` (admin) appends an entry with `ref_seq` to the original. Admins have no other write path to the log.
- **`config_versions` is append-only too** (invariant 9 history). Current config = highest version per section; each change writes an audit entry and requires a reason.
- **Auth:** argon2 passwords, HMAC-signed expiring bearer tokens (stdlib, no JWT dependency). Role is re-read from the DB on every request so deactivation/role changes apply immediately. Mock SSO interface still to do. Login rate limiting is Phase 8.
- **RBAC check by test:** `test_every_non_public_route_has_a_role_guard` fails if any new route lacks `require_roles`.
- **Audit read access:** `admin` and `auditor` only for now; revisit when the staff dashboard (Phase 5) needs supervisor views.
- **Tests need Postgres** (`make db-local`, or the CI service). They create a throwaway `isd_test` DB via Alembic. Tamper tests disable the trigger inside a transaction that is rolled back.
- **Data model scope:** tables for staff, config, residents, cells/devices/assignments, contacts, point events, sanctions (with `issued_by <> confirmed_by` CHECK), appeals, offense flags, audit log. Engine behaviour is Phase 2.
