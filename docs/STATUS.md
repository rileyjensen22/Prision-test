# Status

Last updated: Phase 15 (intake, reentry, outcomes). Everything below was checked by running the code, not from memory.

## Verification run

| Check | Result |
|---|---|
| `pytest` (API, engine, security, simulation) | 487 passed |
| `vitest` | 59 passed |
| Playwright e2e | 61 passed |
| `make lint` (ruff, tsc, eslint, prettier) | clean (after fixing an unused import and formatting in the phone-demo files) |
| `make secrets-check` | no secrets found |
| `make simulate-week` | 26 of 26 checks pass; `not_exercised: []`; audit chain verified before and after the public export |
| Audit-chain verifier | passes (run by the simulated week; also by the audit tests) |

## Phases 9 onward (v1.1)

| Phase | State | Notes |
|---|---|---|
| 9 Audit | **Done** | Report delivered; invariant 14 violation fixed. |
| 10 Reading and chess | **Reading built; chess deferred** | Reader (page, text size, bookmarks, progress sync, offline cache), approved-source catalog, baseline legal and religious texts, optional book points (default 0). Chess is untouched on the owner's instruction. |
| 11 Texting and video | **Built** | Contact requests and approvals, delivery states, keyword flags (review items only), monitored-message review with reasons, attorney messages unreadable by any role, `VideoProvider` with a WebRTC loopback demo, scheduled video, recording retention, on-device tamper detection. See `docs/DECISIONS.md`. |
| 12 Jobs | **Built** | Partner interface (mock), screened public-domain/synthetic tasks, work log, earnings ledger with config split, nightly payouts to the trust account, nightly reconciliation with alerts, Finance page and partner dashboard, sanction-pause flag (off). |
| 13 Scheduling and welfare | **Built** | Per-unit schedule (recreation, programs, visits) with entitlement-based eligibility, officer tap-out/in with bulk actions, who-is-out roster, scheduled-vs-actual report, audited daily export, below-minimum on the dashboard, stored welfare flags that must be acknowledged with an action and escalate to a supervisor after a set time. |
| 14 Education depth | **Built** | Course folders with validator CLI, prerequisites, resume, offline lesson progress, certificates (device list, staff print page), 8 sample courses (5 with Spanish, 2 with a simple level), random question draw with shuffled choices, attempt limit and cooldown, points mapped by level through config. |
| 15 Intake, reentry, outcomes | **Built** | One audited intake step (settings, prior returns with source, offense categories, contacts, keep-separate, cell and device), release countdown on the device, reentry checklist and resources directory from config, cohort outcomes dashboard with outcome entry, pseudonymized researcher export (off by default), import-boundary tests for invariant 17. |
| 16 | **Not started** | |

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
| 12 | Flags only create review items | **Holds, tested** | Keyword rules create `message_flags` rows only; the monitoring and texting code cannot reach the sanction service (tested) and sanction counts do not change. Welfare flags are review items too. |
| 13 | Resident play: no free text, names, wagering, friends | **Partial** | The chess stub has no chat column, method or route (tested). Human play is a mock; the `keep_separate` table now exists (Phase 15, filled at intake) but no matchmaking reads it, no anonymous handles, no match log. Phase 10. |
| 14 | Camera frames never stored; tamper on-device, only during a call | **Holds (fake camera only)** | Detection runs in the kiosk page on brightness numbers, only during an active call; the server accepts only `{signal, covered_ms}` for an active call; no binary column exists in the database. Tested in a browser with a fake camera; real kiosk cameras are untested. Earlier:  The tamper endpoint accepted a report for a call that had already ended and still raised a sanction. It now refuses (`NOT_ACTIVE`, tested). There is no real camera in v1, so on-device detection on a derived signal does not exist yet. Phase 11. |
| 15 | Money paths append-only, nightly reconciliation | **Holds** | The trust ledger and the new earnings ledger are append-only (trigger plus revoked grants plus database checks); the daily job reconciles both every night and a mismatch raises an audit alert, a dashboard banner and a non-zero exit. |
| 16 | Reason required and audit-logged for monitored reads, call review, mirroring | **Holds, one gap** | Messages, call-recording fetch (reason added in Phase 11), the activity timeline and mirroring all need a reason and are logged without content. There is still no screen for reviewing monitored calls. Earlier: | Mirroring and the activity timeline already require a reason and are audit-logged. Staff cannot read monitored message text or review monitored calls at all today (metadata only), so there is no review UI to gate. Phase 11. |
| 17 | Analytics never feed decisions, no risk scores | **Holds, one question** | No analytics tables exist. The welfare check compares a resident's activity with their own recent baseline and shows staff a flag; it feeds no tier, sanction or restriction. See open question 1. |

## Known gaps and TODOs

No `TODO` or `FIXME` markers are in the code. The gaps are the "not done" items in `docs/DECISIONS.md` and `docs/security.md`:

- Rate limits are per process (in memory); a shared store is needed for more than one API process.
- No MFA or password reset for staff.
- Retention: video recordings are purged after `recording_retention_days` (unset keeps them). Messages, call metadata and other records have no retention or deletion job.
- No encryption at rest; backups and restore were never drilled.
- Kiosk lockdown (systemd, TTY, firewall) is documented but untested on a real device.
- Reading level is stored but does not yet change wording (also true of the reader); captions are stored but the demo video call has no captions.
- Chess moves are format-checked only; the engine is a scripted mock. Deferred by the owner: engine licence decision, human matches, `keep_separate`, `games` sanction scope.
- The legal and religious texts are placeholders; there are no Spanish versions yet.
- Docker Compose and `deploy/nginx.conf.example` are untested.
- Seven build-time advisories in the Tailwind 3 chain are accepted until a Tailwind 4 upgrade.
- Compliance items in `docs/ASSUMPTIONS.md` are all unverified and need counsel.
