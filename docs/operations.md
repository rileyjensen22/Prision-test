# Operations

## Environment

| Variable | Meaning | Production rule |
|---|---|---|
| `ISD_ENV` | `dev` (default) or `production` | set to `production` |
| `DATABASE_URL` | the app's database user (`isd_app`): no schema changes, cannot rewrite append-only tables | must not equal the owner URL or contain a development password |
| `MIGRATION_DATABASE_URL` | the schema owner (`isd`): used only by migrations, seeds and the scripts | |
| `SECRET_KEY` | signs staff tokens | random, 32+ characters |
| `PUBLIC_LOG_SALT` | pseudonym key for the public log | random, kept outside the repository; changing it breaks linkage between exports |
| `RESEARCH_SALT` | pseudonym key for the researcher export; must differ from `PUBLIC_LOG_SALT` | random, kept outside the repository |
| `TOKEN_TTL_SECONDS` | staff idle timeout (default 1800) | |
| `MAX_BODY_BYTES` | request size limit (default 1 MiB) | |
| `SSO_MOCK_ENABLED` | mock sign-in | must be `false` |
| `RATE_LIMIT_ENABLED`, `LOGIN_MAX_FAILURES`, `LOGIN_LOCK_SECONDS`, `LOGIN_MAX_PER_MINUTE_IP`, `DEVICE_MAX_PER_MINUTE`, `STAFF_MAX_PER_MINUTE`, `IP_MAX_PER_MINUTE` | rate limits | defaults are sensible |

Generate secrets with `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Never commit them: `make secrets-check` fails the build if something that looks like a secret is committed. The API refuses to start in production with development values.

Run uvicorn behind a reverse proxy with `--proxy-headers --forwarded-allow-ips=<proxy address>` so rate limits see real client addresses. Rate-limit counters are in memory, so until Phase 18 moves them to Postgres a second API process gives every client a second allowance; run several processes only for load tests.

## First deployment

1. Create the two database users and the database (see `scripts/db-init.sql` for the shape; use your own passwords).
2. `make migrate` as the owner user.
3. Load config: seed once (`make seed` in development) or insert config versions through the admin config editor. Production must not use the development seed (it creates predictable device tokens and a shared dev password).
4. Create staff accounts (there is no UI yet; insert with a hashed password, or connect real SSO).
5. Register devices and assign them to cells and residents (staff UI → resident page), then issue each kiosk a token: `python scripts/rotate-device-token.py DEVICE_CODE` or the admin API. Give it to the kiosk as `https://host/resident#device=TOKEN` (see `docs/kiosk.md`).

## Scheduled jobs

| Job | When | Command |
|---|---|---|
| Daily job (clean-day points, tier checks so delayed drops happen, abandoned-call and stale-mirror cleanup) | once a day shortly after midnight UTC | `python scripts/daily-job.py` (`make daily`) |
| Public log export (only if enabled by an operator) | as policy requires | `python scripts/export-public-log.py --out <dir>` |

The daily job also pays work earnings into residents' trust accounts, tops up work tasks, and runs the **nightly reconciliation** (`make reconcile` runs only that). A mismatch makes the job exit with status 2 (so cron or monitoring can alert), writes a `reconciliation_mismatch` audit entry, and shows as a red banner on the staff dashboard and on the Finance page. Nothing is changed automatically: investigate and fix with a correcting entry, then run `make reconcile` again.

Welfare flags are also swept every 15 minutes (`make welfare-sweep`, `scripts/welfare-sweep.py`) so a flag that nobody has acknowledged within `escalate_after_minutes` (default 12 hours) reaches a supervisor even when no one has the staff app open; opening the Welfare page or the dashboard runs the same sweep.

Both are safe to repeat. If the daily job is missed, run it for each missed day (`run_daily(..., for_day=...)`); clean days are never awarded twice.

## Backups and restore

Back up the whole database; encrypt backups and restrict access (operator responsibility). After any restore run the audit verifier (staff UI → Audit log → Verify chain, or `GET /audit/verify`) and `commissary.verify_ledgers`; both must pass. A restore that loses recent audit entries will still verify (the chain is consistent), so compare the last entry number with your records.

## Rotating secrets

- **Staff tokens** (`SECRET_KEY`): changing it signs everyone out; do it if the key may have leaked.
- **Device tokens**: rotate one device with `scripts/rotate-device-token.py`; the old token stops working at once.
- **Public-log salt**: changing it changes every pseudonym, which breaks trends between old and new exports. Rotate only if the old salt may have leaked.
- **Database passwords**: change in the database, then in the environment, then restart.

## Checks you can run

- `make test`: unit, property, API, browser tests and a reduced simulated week.
- `make simulate-week`: the full simulated week (24 residents, 7 days, about 30 seconds). Exit code 0 only if every invariant holds; the report is in `var/simulate-week-report.json`.
- `make secrets-check`: no secrets in the repository.
- `make lint`.

## Performance budget and load test

Budgets (what a person waits for, 95th and 99th percentile, with the stated number of kiosks polling at
the real intervals: view every 30 s, heartbeat every 60 s):

| Request | p95 | p99 |
|---|---|---|
| Kiosk requests (`/device/*`) | 250 ms | 1,000 ms |
| Staff pages (`/staff/*`) | 1,000 ms | 2,500 ms |
| Errors | none | |

`make load-test` (`python scripts/load-test.py`) builds a throwaway database of synthetic residents,
starts the API with four worker processes and drives one asyncio task per device plus five staff
screens, then exits non-zero if any budget is missed. `--speed N` shortens the intervals N times, so
`--devices 500 --speed 3` is the load of 1,500 kiosks.

### Result: 500 devices (2026-10-26, 4 cores, 16 GB, API, Postgres and the load generator on one machine)

`--devices 500 --seconds 60 --speed 1 --workers 4`: **passed**, 1,737 requests, no errors.

| Endpoint | count | p50 | p95 | p99 | max (ms) |
|---|---|---|---|---|---|
| device view | 1,005 | 23 | 33 | 126 | 449 |
| heartbeat | 500 | 8 | 12 | 78 | 213 |
| courses | 111 | 29 | 39 | 62 | 86 |
| staff request | 31 | 9 | 15 | 50 | 50 |
| staff devices | 30 | 45 | 117 | 129 | 129 |
| staff roster | 30 | 140 | 540 | 567 | 567 |
| staff summary | 30 | 141 | 346 | 420 | 420 |

Headroom: at `--speed 3` (the load of 1,500 kiosks on the same machine) the run missed the kiosk
budget slightly (device view p95 351 ms, heartbeat p95 401 ms; no errors, staff pages within budget).
Treat about 1,000 kiosks per 4-core API host as the comfortable limit until the facility-scale
numbers in Phase 20 are recorded.

### What the first run found and what changed

The first run (one worker, speed 5) collapsed: nearly every request timed out. At real speed with one
worker the staff summary took 16 seconds at p95. The cause was the welfare check, which ran several
queries per resident (about 4 seconds for 500 residents, growing linearly). It now loads everything in
a fixed number of queries (`welfare.detect_many`): about 0.1 s cold and 0.04 s warm for the same 500
residents. Same flags, same tests. Running four worker processes removed the
single-process (GIL) ceiling.

Known limits: the staff roster still computes every resident's entitlements on each request (about
150 ms for 500 residents); Phase 20 makes the dashboard summary come from aggregate queries so it does
not grow with the number of residents.
