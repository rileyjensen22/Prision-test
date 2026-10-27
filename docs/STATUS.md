# Status

Last updated: Phase 20 (facility model and scale). Everything below was checked by running the code, not from memory.

## Verification run

| Check | Result |
|---|---|
| `pytest` (API, engine, security, simulation) | 647 passed |
| `vitest` | 79 passed |
| Playwright e2e | 93 passed |
| `make lint` (ruff, tsc, eslint, prettier) | clean (after fixing an unused import and formatting in the phone-demo files) |
| `make secrets-check` | no secrets found |
| `make simulate-week` | 26 of 26 checks pass; `not_exercised: []`; audit chain verified before and after the public export |
| Audit-chain verifier | passes (run by the simulated week; also by the audit tests) |

## Phases 9 onward (v1.1)

| Phase | State | Notes |
|---|---|---|
| 9 Audit | **Done** | Report delivered; invariant 14 violation fixed. |
| 10 Reading and chess | **Built** | Reader (page, text size, bookmarks, progress sync, offline cache), approved-source catalog, baseline legal and religious texts, optional book points (default 0). Chess finished in Phase 19: own alpha-beta engine on chess.js (BSD-2) with five levels that works offline, human matches paired by the server under the keep-separate, same-line and staff-switch rules, server-checked moves, anonymous handles, move/draw/resign only, match log, `games` sanction scope. |
| 11 Texting and video | **Built** | Contact requests and approvals, delivery states, keyword flags (review items only), monitored-message review with reasons, attorney messages unreadable by any role, `VideoProvider` with a WebRTC loopback demo, scheduled video, recording retention, on-device tamper detection. See `docs/DECISIONS.md`. |
| 12 Jobs | **Built** | Partner interface (mock), screened public-domain/synthetic tasks, work log, earnings ledger with config split, nightly payouts to the trust account, nightly reconciliation with alerts, Finance page and partner dashboard, sanction-pause flag (off). |
| 13 Scheduling and welfare | **Built** | Per-unit schedule (recreation, programs, visits) with entitlement-based eligibility, officer tap-out/in with bulk actions, who-is-out roster, scheduled-vs-actual report, audited daily export, below-minimum on the dashboard, stored welfare flags that must be acknowledged with an action and escalate to a supervisor after a set time. |
| 14 Education depth | **Built** | Course folders with validator CLI, prerequisites, resume, offline lesson progress, certificates (device list, staff print page), 8 sample courses (5 with Spanish, 2 with a simple level), random question draw with shuffled choices, attempt limit and cooldown, points mapped by level through config. |
| 15 Intake, reentry, outcomes | **Built** | One audited intake step (settings, prior returns with source, offense categories, contacts, keep-separate, cell and device), release countdown on the device, reentry checklist and resources directory from config, cohort outcomes dashboard with outcome entry, pseudonymized researcher export (off by default), import-boundary tests for invariant 17. |
| 16 | **Built** | Device pairing with one-time codes, heartbeats, staff pause/restart, kiosk provisioning script (tested as files only), structured logs, per-address rate limits, backup and restore drill, load test. Threat model, OTA design, admin guide and compliance gap report written in Phase 17. |
| 21 | **Built** | UI overhaul finished on this branch: design tokens, Atkinson Hyperlegible, lucide icons, native-dialog sheets, day and night themes, staff data tables, English and Spanish. The last sentence-level staff strings are now translated (hard-coded text 74 to 26; the 26 left are all on the internal style-guide page, which is a developer reference left in English). The flaky schedule e2e is fixed (its second kiosk shared browser storage and overwrote the first one's device token). axe, overflow and visual-regression specs pass. See `docs/ui/direction.md`. |
| 20 | **Built** | Facility model (site, hub, line, floor, cell, recreation rooms) from `config/facility.yaml`: 5 hubs x 6 lines x 4 floors x 16 cells = 1,920 cells; dashboard grouped by hub, line and floor; roster paged and filtered; per-floor recreation with a yard concurrency limit; `make seed` (small) and `make seed-full`; load test at full size (1,732 kiosks) passes the budgets. See `docs/facility.md`, `docs/operations.md`. |
| 19 | **Built** | Chess: see Phase 10 and invariant 13. Own MIT engine on chess.js (BSD-2) with five levels, offline; human matches with server-checked moves (own rules module, perft-verified), anonymous handles, keep-separate and same-line pairing rules, staff switches per facility, unit and resident, `games` sanction scope, match log and staff page, nullable `line_code` on cells. |
| 18 | **Built** | Resident vacate and transfer, keep-separate screen, monitored-call review (role and reason; attorney calls never listed), retention jobs from compliance config, staff TOTP MFA with recovery codes and admin password reset, shared Postgres rate limits, AES-GCM encryption at rest with key rotation, reading levels change wording in courses and the reader, demo captions in the video call, Spanish legal and religious placeholder texts, outcomes CSV import (preview, all-or-nothing, append-only), reentry offline from the saved copy, reentry as a named baseline feature, no daily quiz cap on basic courses. |
| 17 | **Built** | Owner questions answered (`docs/owner-questions.md`); `docs/threat-model.md`, `docs/ota-design.md`, `docs/admin-guide.md`, `docs/compliance-gap-report.md`; load test passes at 500 devices (`docs/operations.md`); welfare detection made set-based after the first run exposed a 4 second cost. |

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

## Invariants 1 to 11

All hold. Each has a test, and the simulated week re-checks 1, 2, 3, 4, 5, 6, 7, 8 and 11 end to end. No deviations.

## Invariants 12 to 17 (added in v1.1)

| # | Rule | State | Detail |
|---|---|---|---|
| 12 | Flags only create review items | **Holds, tested** | Keyword rules create `message_flags` rows only; the monitoring and texting code cannot reach the sanction service (tested) and sanction counts do not change. Welfare flags are review items too. |
| 13 | Resident play: no free text, names, wagering, friends | **Holds, tested** | The match API accepts only a coordinate move, a draw action, resign, and an engine level (every other field refused; an OpenAPI test checks no free-text field exists). Residents see a random per-match handle, never a name or code. No spectator route. No stake column. Pairing refuses keep-separate pairs, same-line residents and residents with no line (tested, and re-checked by the simulated week). Leaving costs nothing. |
| 14 | Camera frames never stored; tamper on-device, only during a call | **Holds (fake camera only)** | Detection runs in the kiosk page on brightness numbers, only during an active call; the server accepts only `{signal, covered_ms}` for an active call; no binary column exists in the database. Tested in a browser with a fake camera; real kiosk cameras are untested. Earlier:  The tamper endpoint accepted a report for a call that had already ended and still raised a sanction. It now refuses (`NOT_ACTIVE`, tested). There is no real camera in v1, so on-device detection on a derived signal does not exist yet. Phase 11. |
| 15 | Money paths append-only, nightly reconciliation | **Holds** | The trust ledger and the new earnings ledger are append-only (trigger plus revoked grants plus database checks); the daily job reconciles both every night and a mismatch raises an audit alert, a dashboard banner and a non-zero exit. |
| 16 | Reason required and audit-logged for monitored reads, call review, mirroring | **Holds** | Messages, call-recording fetch (reason added in Phase 11), the activity timeline and mirroring all need a reason and are logged without content. The call-review screen (Phase 18) is gated by role and reason and never lists attorney calls. Earlier: | Mirroring and the activity timeline already require a reason and are audit-logged. Staff cannot read monitored message text or review monitored calls at all today (metadata only), so there is no review UI to gate. Phase 11. |
| 17 | Analytics never feed decisions, no risk scores | **Holds** | No analytics tables exist. The welfare check compares a resident's activity with their own recent baseline and shows staff a flag; it feeds no tier, sanction or restriction. (The owner closed the earlier question: no change needed.) |

## Known gaps and TODOs

No `TODO` or `FIXME` markers are in the code. The gaps are the "not done" items in `docs/DECISIONS.md` and `docs/security.md`:

- Retention periods are unset in the real config (counsel decides); the jobs exist and are tested. Disk and backup encryption are the operator's.
- Kiosk lockdown (systemd, TTY, firewall) is documented but untested on a real device.
- Chess: line codes on cells are set by staff until Phase 20 derives them from the facility model; a cell with no line is never paired. The built-in engine is modest by design (search depth 4 at most, 1.5 s per move); a stronger engine or an outside chess service would plug in behind `ChessProvider`.
- The legal and religious texts are placeholders. Spanish versions exist and are labelled unofficial translations (Reina-Valera 1909 for the Psalm); counsel must verify them.
- Docker Compose and `deploy/nginx.conf.example` are untested.
- Seven build-time advisories in the Tailwind 3 chain are accepted until a Tailwind 4 upgrade.
- Compliance items in `docs/ASSUMPTIONS.md` are all unverified and need counsel.
