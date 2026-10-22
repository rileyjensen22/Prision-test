# Status

Last audit: Phase 9 (v1.1). Everything below was checked by running the code, not from memory.

## Verification run

| Check | Result |
|---|---|
| `pytest` (API, engine, security, simulation) | 248 passed |
| `vitest` | 33 passed |
| Playwright e2e | 37 passed |
| `make lint` (ruff, tsc, eslint, prettier) | clean (after fixing an unused import and formatting in the phone-demo files) |
| `make secrets-check` | no secrets found |
| `make simulate-week` | 19 of 19 checks pass; `not_exercised: []`; audit chain verified before and after the public export |
| Audit-chain verifier | passes (run by the simulated week; also by the audit tests) |

## Phases 0 to 8

| Phase | State | Notes |
|---|---|---|
| 0 Scaffold | **Built** | Docker Compose is written but has never been run in this environment (no Docker). Local Postgres path (`make db-local`) is what was tested. |
| 1 Foundation | **Built** | Append-only audit and config tables, hash chain, RBAC, argon2 passwords. |
| 2 Engine | **Built** | Property tests cover baseline never removed, ceiling monotonic, one tier drop per week, issuer is not confirmer. |
| 3 Resident shell | **Built** | Kiosk UI, i18n (en, es), offline cache that fails closed. |
| 4 Features | **Built** | Education loop, mock calls, mock commissary with append-only ledger. |
| 5 Staff app | **Built** | Dashboard, confirmations, appeals, outliers, config editor. |
| 6 View-as | **Built** | Sandbox causes zero writes (tested); mirror sessions are logged. |
| 7 Transparency and stubs | **Partial** | Public log, welfare flags, out-of-cell log, compliance config and ASSUMPTIONS.md are built. Texting, video, chess, reading, jobs and rec are **stubs** (data model, interface, thin UI). Phases 10 to 13 replace them. |
| 8 Hardening | **Partial** | Rate limiting, CSP, production guard, secrets scan, kiosk doc and the simulated week are done. The kiosk was never tested on a real Linux device, and MFA, shared rate-limit store, retention jobs and encryption at rest are not done (see `docs/security.md`). |

Extra, not in the original phases: a phone-viewable demo of the resident UI (`web/src/demo`, `scripts/build-demo.py`, `scripts/record-demo-fixtures.py`). It uses recorded synthetic responses and is not part of the product.

## Invariants 1 to 11

All hold. Each has a test, and the simulated week re-checks 1, 2, 3, 4, 5, 6, 7, 8 and 11 end to end. No deviations.

## Invariants 12 to 17 (added in v1.1)

| # | Rule | State | Detail |
|---|---|---|---|
| 12 | Flags only create review items | **Holds, nothing to break yet** | There are no keyword rules. Welfare flags are review items that nothing acts on automatically. Phase 11 adds keyword flags and must keep this. |
| 13 | Resident play: no free text, names, wagering, friends | **Partial** | The chess stub has no chat column, method or route (tested). Human play is a mock; there is no `keep_separate` table, no anonymous handles, no match log. Phase 10. |
| 14 | Camera frames never stored; tamper on-device, only during a call | **Was violated, now fixed** | The tamper endpoint accepted a report for a call that had already ended and still raised a sanction. It now refuses (`NOT_ACTIVE`, tested). There is no real camera in v1, so on-device detection on a derived signal does not exist yet. Phase 11. |
| 15 | Money paths append-only, nightly reconciliation | **Partial** | The trust ledger is append-only (trigger plus revoked grants, `balance_after >= 0`). There is **no nightly reconciliation job** and no job-earnings ledger. Phases 12 and 16. |
| 16 | Reason required and audit-logged for monitored reads, call review, mirroring | **Partial** | Mirroring and the activity timeline already require a reason and are audit-logged. Staff cannot read monitored message text or review monitored calls at all today (metadata only), so there is no review UI to gate. Phase 11. |
| 17 | Analytics never feed decisions, no risk scores | **Holds, one question** | No analytics tables exist. The welfare check compares a resident's activity with their own recent baseline and shows staff a flag; it feeds no tier, sanction or restriction. See open question 1. |

## Known gaps and TODOs

No `TODO` or `FIXME` markers are in the code. The gaps are the "not done" items in `docs/DECISIONS.md` and `docs/security.md`:

- Rate limits are per process (in memory); a shared store is needed for more than one API process.
- No MFA or password reset for staff.
- No retention or deletion jobs; `recording_retention_days` is a config value only.
- No encryption at rest; backups and restore were never drilled.
- Kiosk lockdown (systemd, TTY, firewall) is documented but untested on a real device.
- Reading level is stored but does not yet change wording; captions are stored but there is no video to caption.
- Chess moves are format-checked only; the engine is a scripted mock.
- Docker Compose and `deploy/nginx.conf.example` are untested.
- Seven build-time advisories in the Tailwind 3 chain are accepted until a Tailwind 4 upgrade.
- Compliance items in `docs/ASSUMPTIONS.md` are all unverified and need counsel.
