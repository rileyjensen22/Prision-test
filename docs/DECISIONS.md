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

## Phase 2

- **Pure engine, thin services.** `api/isd/engine/` is I/O-free (config, ceiling, tiers, entitlements, authority) so Hypothesis can hammer it. `services/` loads facts, persists decisions, and writes audit entries. A test fails if anything outside `entitlement_service` calls `compute_entitlements` (invariant 2).
- **`get_entitlements(session, resident_id, at_time)` is read-only** (tested), so Phase 6 sandbox/time-travel is safe. It never writes tier changes; `points.evaluate_tier` does, and runs after each point event. A daily job (Phase 8 `simulate-week`) must also call it so a deferred weekly drop eventually happens.
- **Earned tier vs effective tier.** Earned tier follows points (with hysteresis). Effective tier = `min(earned, repeat-return ceiling)`. The ceiling never lowers points or earned tier. Reasons distinguish `TIER_LOCKED` (not yet earned) from `TIER_CEILING` (earned but capped).
- **Tier history table** (`tier_history`) instead of a mutable `earned_tier` column: the current tier and the last drop time are derived, so the 7-day drop rule is checkable from data. Promotion may jump several tiers; a drop is always exactly one level, and drops are at least 7 days apart (boundary inclusive).
- **Sanction vs points are separate.** A sanction only locks features. When a sanction becomes active (immediately, or on confirmation) a `confirmed_{minor|major}_infraction` point event is recorded. Overturning on appeal records an `infraction_reversal` event. Assumption: severity per infraction code is in `config/sanctions.yaml` (`DISRUPT`, `CELL_MESS`, `STAFF_DISRESPECT` = minor; `CAM_BLOCK`, `DEVICE_TAMPER`, `DEVICE_DAMAGE` = major). The spec didn't assign severities, so this needs customer sign-off.
- **Authority rules.** Needs a supervisor if the rule isn't `officer_immediate` or lasts over 24h. Evidence is required at issue time: a system event, or a report from a second staff member (not the issuer). `DEVICE_TAMPER` accepts only a system event. Once an officer hits the weekly cap (default 3 immediate sanctions in a rolling 7 days) further sanctions become `pending` for supervisor confirmation, rather than being refused. Only supervisors confirm, reject, or review appeals; the DB also has a CHECK that issuer ≠ confirmer. System-detected events may issue (never confirm). Rejected: letting admins confirm (spec says supervisor).
- **Lock starts at confirmation**, not at issue, for pending sanctions; end time = start + duration.
- **Appeals** can only be filed against active sanctions, one open at a time, and are due in `appeal_review_hours`. `overdue_appeals()` is available for the dashboard.
- **Config validation** now rejects unknown sanction scopes and any offense restriction that names a baseline feature.
- **Feature catalog** (`engine/features.py`) is the only definition of the protected baseline. Steps 3–5 of the composition only operate on non-baseline features, and property tests assert the baseline is never removed.
- **Contact-level blocks** are returned as `blocked_contact_ids` (they're per-contact, not per-feature) and apply at every tier.
- **Not yet done (later phases):** clean-day awards (needs the daily job), `valid_until` for the offline snapshot (Phase 3; `next_change_at` is the building block), HTTP routes for sanctions/appeals (Phase 5).
