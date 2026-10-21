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

## Phase 3

- **Device identity by token.** Kiosk routes (`/device/*`) are authenticated by a per-device secret (hash stored in `devices.token_hash`), then resolved device -> open assignment -> resident. Rejected: unauthenticated device code (anyone on the network could read a resident's screen). The RBAC route-guard test accepts either a staff role guard or the device guard.
- **One payload, one code path.** `build_resident_view()` produces the `ResidentView` the kiosk renders. Phase 6 sandbox/mirror will call the same function (a test confirms `simulation` is the only field that differs).
- **Offline = fail closed.** `valid_until` = min(next sanction boundary, now + TTL). Past it with no connection, non-baseline features are paused client-side (`OFFLINE_STALE`). Rejected: trusting the cache indefinitely (a lock that should have started or ended would be wrong), or locking everything including baseline (violates invariant 1).
- **Server-time offset.** Staleness uses `Date.now() + (server generated_at - device time at fetch)`. This came out of the e2e offline test: a skewed device clock would otherwise extend or cut short the cache.
- **Appeals and Request staff are idempotent for offline replay.** Staff requests carry a `client_id` (unique); a duplicate appeal returns 409, which the queue treats as delivered.
- **Tier-locked vs restricted.** "Not unlocked yet" appears on the service tile only; the Restrictions list shows sanctions, offense restrictions, and the ceiling. Offense restrictions show the config `reason_text` (English only for now; localizing it needs a per-language field in the offense config).
- **Allowances show `used: 0`** until calls and commissary track usage in Phase 4.
- **Reading level** is stored and sent but not yet used to switch wording; captions flag is stored for video (stub). Both are staff-set only.
- **Staff-controlled settings and assignments** have API routes now (`PUT /staff/residents/{id}/settings`, `POST /staff/device-assignments`); both are audit-logged with a required reason. The staff UI for them is Phase 5.
- **E2E runs the real stack.** Playwright seeds a fresh `isd_e2e` database, serves the API with uvicorn on :8001 and the production web build on :4173, so the CSP and API contract are both exercised.
- **Known gap:** no login/rate limiting on device routes yet (Phase 8), and the device token lives in localStorage.

## Phase 4

- **Content and policy are versioned config.** Two new sections, `courses` (lessons, quiz, answers; bilingual) and `commissary` (catalog, prices in cents, per-item `min_tier` and blocked offense categories, `max_deposit_cents`). Edits are audit-logged like any config. Rejected: separate content tables (would duplicate versioning). Quiz answers are readable by staff roles via the config API but never sent to the device (tested). `load_engine_config` now loads only the sections the engine needs, and `seed_database` adds any missing section, so older databases keep working.
- **Education.** One sample basic course (`MONEY101`, +50) as specified, plus a tiny advanced course (`WORKMATH`) so gating can be shown; delete it if you want strictly one. Basic courses are gated by the baseline `basic_education` feature (never locks); advanced and program courses by `advanced_education`. Completion awards points once (unique per resident and course), through the normal point-event path so promotion and the weekly-drop rules apply. The demo loop needs a resident near a threshold: with the seed values one course (+50) cannot promote from 0 points, so the demo resident starts at 60. Quiz grading is server-side, so education needs a connection in v1 (offline lessons are a later option).
- **Attorney privilege enforced in layers (invariant 6).** (1) `TelephonyService` is the only path to a provider; for privileged calls it tells the provider not to record, never asks for monitoring data, hangs up and raises if a provider captured anyway, and refuses `recording()`. (2) The DB has CHECK constraints: a privileged call can't be `monitored` and can't have a `monitor_ref`. (3) `call_records` has no content columns (tested). (4) Staff access to call content (`fetch_recording`) is audit-logged, limited to supervisor/admin, and for attorney calls only logs a `monitoring_denied` entry with the call id. What is kept for attorney calls: that a call happened, the contact record, start/end, duration. Providers only receive an opaque phone reference.
- **Attorney contacts ignore no-contact blocks and the tier allowance.** Steps 3-5 never remove baseline, so an attorney call can't be blocked or metered. Which contacts count as attorney comes from `compliance.privileged_contact_types`.
- **Call limits.** Daily allowance = tier minutes; usage is the sum of today's non-attorney call seconds, shown in whole minutes rounded up. Each call is capped at the minutes left; the server clamps duration, and an abandoned call is closed at its cap. One call at a time per resident. Days and weeks are UTC for now (a facility time zone is a config item for later).
- **Monitoring notice.** Regular calls display "may be monitored and recorded" before and during the call; attorney calls display that they are private. Wording needs counsel review.
- **Commissary money is integer cents** in an append-only `trust_ledger` (UPDATE/DELETE/TRUNCATE blocked by trigger and revoked grants; DB CHECK for no overdraft). Entries are written under a per-resident advisory lock, each carrying `balance_after`; `verify_ledgers()` re-checks every balance and that each order matches its ledger entry (used by `simulate-week` in Phase 8). Orders are idempotent per `client_id`.
- **Order rules.** Commissary must be allowed by the entitlement engine; each item checks `min_tier` against the resident's effective tier and blocked offense categories; the order must fit the balance and the weekly dollar limit (`dollars_per_week`, ISO week in UTC). Entitlements now also return the resident's offense categories for this. Refunds exist as a ledger type but have no workflow yet.
- **Deposits** go through `PaymentProvider` (mock, deterministic ids). `POST /mock/deposits` (supervisor or admin) stands in for a family-payment webhook; it is idempotent on `idempotency_key`, bounded by `max_deposit_cents`, and audit-logged.
- **Telephony and payments are mocks behind interfaces** (`isd/interfaces`, `isd/mocks`), chosen in `isd/providers.py`. No network calls anywhere.
- **Not yet done:** texting/video/chess/reading/jobs stubs (Phase 7), staff views of calls and ledgers (Phases 5-7), clean-day points (daily job).
