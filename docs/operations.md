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

Run uvicorn behind a reverse proxy with `--proxy-headers --forwarded-allow-ips=<proxy address>` so rate limits see real client addresses. Run **one** API process (or move the rate-limit counters to a shared store).

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
