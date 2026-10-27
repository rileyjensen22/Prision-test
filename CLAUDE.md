# ISD v1: Resident Device Operating Environment

> "ISD" is a placeholder product name. Version 1 is a **working prototype/demo**, not a production deployment.

## 1. What we are building

A wall-mounted, touch-first device for single-occupancy cells, plus a staff web dashboard and an API. Residents spend most of the day alone in the cell. The device gives them education, reading, chess, commissary, and monitored contact with the outside world, and unlocks more of it through a **ten-tier system** driven mostly by automated rules (finish a course, earn more phone time).

Goals: improve quality of life in the cell, build skills, reduce reoffending, and make every staff decision visible and auditable.

Customers: other correctional facilities, and facilities we run ourselves. Initial market: US southern states (e.g. Georgia).

## 2. Invariants (never violate; each has a test)

1. **Protected baseline never locks.** These stay on at every tier and under every sanction: legal materials/law library, grievances and appeals, medical and mental-health requests, "request staff" button, emergency contact, religious texts, basic education (it also earns points, so there is always a path up), attorney calls, and the minimum out-of-cell time setting.
2. **One entitlement function.** All feature access flows through `get_entitlements(resident, at_time)`. Feature code never checks tier or sanctions directly.
3. **Append-only audit log.** No UPDATE or DELETE on audit tables, for anyone including admins. Mistakes are fixed by a new correcting entry that references the original. Hash-chain the entries and enforce append-only at the database level (revoked grants plus a trigger).
4. **No single staff member can impose a significant sanction.** See section 6.
5. **Every lock shows the resident a reason code, an end time, and how to appeal.**
6. **Attorney communications are never recorded, transcribed, scanned, or content-logged.** Enforced in the telephony/messaging interface, not just the UI. Only that a call occurred and its duration may be kept.
7. **Jobs/work never affects tier or entitlements.** Participation is voluntary, and declining creates no points event.
8. **Tier loss is gradual.** The earned tier drops at most one level per rolling 7 days. Temporary sanctions lock features without erasing tier or points.
9. **Everything tunable lives in versioned config tables**, not code: tiers, limits, point values, thresholds, sanctions, offense restrictions, repeat-return curve. Config changes are audit-logged.
10. **Externals are mocked behind interfaces:** telephony, video, payments, chess provider, facility camera events, content sources.
11. **Synthetic data only.** No real names, IDs, or records anywhere in the repo.
12. **Automated flags only create review items.** Keywords and unusual patterns never create a sanction on their own; a human confirms.
13. **Resident-to-resident play has no free text, no real names, no wagering, no friend lists.** Pairing respects keep-separate records.
14. **Device camera frames are never stored or transmitted** except as the live call itself. Tamper detection runs on-device on a derived signal (e.g. brightness/variance) and only during an active call.
15. **Money paths are append-only** (trust ledger, job earnings). A nightly reconciliation job checks that balances match the ledger and alerts on any mismatch.
16. **Reading monitored messages, reviewing monitored calls, and mirroring a device each require a stated reason**, and each is audit-logged.
17. **Analytics are for evaluation only.** They never feed into tier, sanction, or restriction decisions, and there are no individual risk scores.

## 3. Stack and layout

- **Frontend:** React + TypeScript (Vite), one app with two surfaces: `/resident` (kiosk) and `/staff`. Tailwind. i18n from day one (English, Spanish).
- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, Pydantic v2.
- **Database:** PostgreSQL. **Tests:** pytest, Hypothesis (property tests), Playwright (e2e), Vitest.
- **Dev:** Docker Compose, Makefile, GitHub Actions CI.
- **Kiosk target:** fullscreen browser (Chromium kiosk mode on Linux later). Resident UI has no address bar, no external navigation, and a strict CSP limited to our origin plus allowlisted content hosts. Document the kiosk launch command in `docs/kiosk.md`. Do not build a custom OS in v1.

```
/api            FastAPI app (routers, services, engine, interfaces, mocks)
/web            React app (resident + staff)
/config         seed YAML: tiers, points, sanctions, offenses, compliance
/content        course folders (docs/courses.md)
/docs           ASSUMPTIONS.md, DECISIONS.md, kiosk.md, architecture.md
/scripts        seed, simulate-week, export-public-log, daily-job, check-secrets, rotate-device-token
/deploy         example reverse-proxy config (untested example)
```

## 4. Core domain

### 4.1 Entitlements

`get_entitlements()` returns, per feature: `allowed`, `limits` (minutes, messages, dollars), and `reasons[]` (reason codes for every lock). Composition order:

1. Start with the **protected baseline**.
2. Add tier grants, capped at the resident's **tier ceiling** (4.4).
3. Subtract **offense restrictions** (4.5).
4. Subtract **active sanctions** (4.3).
5. Subtract **contact-level blocks** (no-contact orders), which apply at any tier.

Steps 3 to 5 can never remove anything in the protected baseline.

### 4.2 Points and tiers

- Residents earn points from events: system-detected (course completions, clean days) or staff-entered (commendations, confirmed infractions).
- Promotion happens when points cross the next threshold. Demotion thresholds sit lower than promotion thresholds (hysteresis, default 15%), so tiers don't flicker.
- Demotion follows invariant 8.
- Seed values (all tunable):

| Event | Points |
|---|---|
| Clean day (no confirmed infraction) | +2 |
| Basic course completed | +50 |
| Advanced course completed | +100 |
| Program/certificate completed | +200 |
| Staff commendation (reason required, max 3/week) | +10 |
| Confirmed minor infraction | -25 |
| Confirmed major infraction | -100 |

Tier thresholds (T1 to T10): `0, 100, 250, 450, 700, 1000, 1400, 1900, 2500, 3200`.

### 4.3 Sanctions

A sanction locks a **scope** (feature set) for a **duration**. It never touches points or earned tier. Seed infraction codes:

| Code | Scope locked | Duration | Confirmation |
|---|---|---|---|
| DISRUPT (disruptive behavior) | communication | 24h | officer, immediate |
| CELL_MESS (cell sanitation) | commissary | 24h | officer, immediate |
| STAFF_DISRESPECT | communication | 24h | **supervisor always** (highly subjective) |
| CAM_BLOCK (facility cell camera obstructed) | all non-baseline | 48h | supervisor + evidence |
| DEVICE_TAMPER (device camera covered during a call) | video | 72h | system event, supervisor confirms |
| DEVICE_DAMAGE | all non-baseline | 7d | supervisor + evidence |

### 4.4 Repeat-return ceiling

Residents who come back lose a little at first and more each time, trending toward nothing but the baseline.

```
n = prior_returns (staff-entered at intake, source noted, audit-logged)
ceiling_tier = clamp( round( 10 * (1 - (n / N) ** p) ), 1, 10 )
defaults: N = 12, p = 1.5
```

This gives `10, 9, 9, 8, 7, 6, 6, 5, 4, 2, 1, 1` for n = 1..12. Unit-test that the ceiling is non-increasing in n and that the raw loss per step grows. The resident can still climb by points up to the ceiling. The protected baseline is unaffected. The resident's screen shows the ceiling and why. Make `N` and `p` editable in config, and log every edit.

### 4.5 Offense-based restrictions

Table: `offense_category`, `blocked_features[]`, `reason_text` (shown to the resident), `required_reviewer_role`, `review_interval_days`. Seed 2 to 3 clearly labeled placeholder rows. Real categories come from the customer. Residents see which restrictions apply and why, at the offense-category level only, with no case details.

### 4.6 Seed tier feature matrix (tunable)

| Tier | Calls min/day | Texts/day | Video min/week | Commissary $/week | Chess | Outdoor rec |
|---|---|---|---|---|---|---|
| 1 | 15 | 0 | 0 | 20 | none | none |
| 2 | 20 | 0 | 0 | 30 | vs engine | none |
| 3 | 30 | 0 | 0 | 40 | vs engine | none |
| 4 | 30 | 10 | 0 | 50 | vs engine | none |
| 5 | 40 | 20 | 0 | 60 | + human (no chat) | none |
| 6 | 45 | 30 | 30 | 75 | same | none |
| 7 | 60 | 40 | 60 | 90 | same | none |
| 8 | 60 | 50 | 90 | 110 | same | none |
| 9 | 75 | 60 | 120 | 130 | same | 1 h/day |
| 10 | 90 | 75 | 180 | 150 | same | 2 h/day |

Also: general reading library from T1, expanded catalog from T4. Advanced education catalog from T3. Basic education is baseline. All residents get the baseline daily out-of-cell time (default 60 min, a config value). Higher tiers add outdoor rec on top.

## 5. Staff roles

`officer`, `supervisor`, `admin`, `auditor` (read-only, including audit and transparency data). RBAC enforced server-side on every route. Staff passwords hashed with argon2. Mock SSO behind an interface.

## 6. Authority rules (guard-abuse containment)

- **Minor sanction** (lock of 24h or less, code marked officer-immediate): applies immediately. Capped per officer per rolling week (default 3, configurable).
- **Anything larger, and anything marked supervisor-always:** needs supervisor confirmation plus evidence, either a system-detected event or a second staff member's report. Issuer and confirmer must be different people.
- **Reason code** shown to the resident on every sanction.
- **Appeals:** the resident files from the device (baseline feature). Reviewed by someone other than the issuer within a configurable window (default 72h). Outcomes are new log entries, never edits.
- **Outlier dashboard:** each officer's report rate, sanction rate, and appeal-overturn rate versus peers, with outliers flagged to supervisors and admins.
- **No overrides of the log.** Admins can add correcting entries only.

## 7. Resident experience

- Touch-first, large targets, high contrast, plain language, English and Spanish.
- Per-resident settings (language, text size, reading level, captions) are changed by **staff**. Residents cannot change them.
- Resident identity comes from the **device-to-cell-to-resident assignment** made by staff. No login. Assignment changes are audit-logged. Document this as an assumption to revisit.
- Home screen: current tier, points to next tier, daily/weekly allowances remaining, active locks with reason and end time, "Why is this locked?" and "Appeal" actions, and a persistent **Request staff** button.
- Returns to home after inactivity.
- **Sync:** online by default. The device keeps a local event queue and a cached entitlement snapshot with a `valid_until` timestamp, so locks still apply offline. Calls and video require connectivity. Staff see "last synced" per device and get an alert after a configurable offline period.

## 8. Features

**End to end in v1:**

1. **Education.** One sample basic course (lessons plus quiz). Completion creates a points event, which can trigger promotion and visibly raises call minutes. This is the demo loop.
2. **Calls.** Mock telephony behind a `TelephonyProvider` interface. Approved-contact list with contact types (`family`, `friend`, `attorney`). Per-tier daily limits. Non-attorney calls flagged `monitored=true`. Attorney calls flagged `privileged=true` with no content capture. Contact-level blocks honored.
3. **Commissary.** Mock trust-account ledger (append-only entries). Mock deposit endpoint simulating family deposits behind a `PaymentProvider` interface. Weekly spend limit per tier. Item restrictions per tier and per offense.

**Stubbed in v1 (UI placeholder, data model, interface; no real implementation):**

- Texting (monitored; tier-gated)
- Video calls (device camera active only during a call; tamper event ends the call and creates a DEVICE_TAMPER event)
- Chess (engine plus human with no chat; `ChessProvider` interface for a future chess.com-style partnership)
- Reading library (bundle a few public-domain texts; allowlist table `approved_content_sources`, since all outside content is pre-approved)
- Jobs (see 8.1)
- Rec-time scheduling

### 8.1 Jobs (separate from tiers)

Stub only: `job_listings`, voluntary opt-in, configurable pay split (resident / facility / deductions as config, not hardcoded), and a test proving that declining or leaving a job generates no points or sanction event. Task design must avoid exposing third-party personal data (no customer-support-style work that handles real customers' data). Candidate task types: transcription of public-domain material, captioning, labeling of non-personal data. Mark compliance review as required in `docs/ASSUMPTIONS.md`.

## 9. Staff dashboard

- Roster by cell: tier, points, ceiling, active sanctions, last sync.
- Event feed and a **pending confirmations queue** for supervisors.
- Sanction/appeal workflow per section 6, plus the officer outlier view.
- Resident activity timeline (calls, features used, durations). Monitored message and call metadata available to authorized roles. Monitoring access is itself audit-logged.
- Config editor for tiers, limits, points, infraction codes, offense restrictions, and repeat-return curve (versioned, audit-logged).
- Facility event ingest through a `FacilityEventSource` interface (mock in v1). This is how events from the facility's own cell cameras enter the system, for example `camera_obstruction`. The software does not run cell cameras.

### 9.1 View as resident

1. **Sandbox mode:** staff pick a real or synthetic resident and override tier, language, restrictions, and sanctions, and optionally time-travel. The resident UI renders from the entitlement engine in a **read-only dry run**, with no writes or side effects and a persistent "SIMULATION" banner.
2. **Live mirror:** a read-only mirror of a real device's current screen, clearly labeled, with every mirror session audit-logged (who, which resident, when, how long).

Implement by making the resident UI render from a single `ResidentView` payload from the API, so both modes use the same code path.

## 10. Transparency and audit

- Audit entries cover sanctions, confirmations, appeals, overrides-by-correction, config changes, monitoring access, mirror sessions, and assignment changes. Include the actor, role, target, reason code, and prior-entry reference.
- **Public log export** (operator toggle, **off by default**): static JSON/CSV plus a simple public page with pseudonymized resident IDs, reason codes, durations, outcomes, and aggregate stats per role. No names, no case details. Script: `scripts/export-public-log`.

## 11. Welfare and out-of-cell tracking

The standard regime is about 23 hours in cell, which many jurisdictions and the UN Mandela Rules classify as restrictive housing/solitary. Customers' lawyers and regulators will ask for records. So:

- `out_of_cell_log`: facility-entered (or ingested) minutes per resident per day. Dashboard flags residents below the configured minimum (`min_out_of_cell_minutes_per_day`, default 60).
- **Welfare flag:** auto-surface to staff when a resident's device usage and contact drop sharply versus their own baseline, or when there has been no contact for a configurable number of days.
- "Request staff" and medical/mental-health request are always available (baseline).
- Write the regime and these safeguards into `docs/ASSUMPTIONS.md` for counsel review.

## 12. Compliance hooks (not blockers for v1)

Create `config/compliance.yaml` and `docs/ASSUMPTIONS.md`. Treat every item as **unverified; confirm with counsel before any deployment**:

- Federal rules on incarcerated-people communications services (rate caps, accessibility, privileged-call handling), and any state or contract rules
- ADA accessibility, PREA, data retention, and restrictive-housing statutes in the target state
- Rules on work programs, wage deductions, and voluntariness
- Public-records and transparency obligations
- Procurement and security requirements of state corrections departments

Config keys to include: `call_rate_cap_per_minute` (null), `recording_retention_days`, `privileged_contact_types`, `min_out_of_cell_minutes_per_day`, `appeal_review_hours`, `officer_weekly_immediate_sanction_cap`, `public_log_enabled`, `offline_alert_minutes`.

## 13. Build phases

Work one phase at a time. Don't start the next until the current phase's tests pass and `docs/DECISIONS.md` is updated.

| Phase | Deliver | Done when |
|---|---|---|
| 0. Scaffold | Repo layout, Docker Compose, Makefile, CI, lint/format, seed script with synthetic data | `make dev`, `make test`, `make seed` all work |
| 1. Foundation | Data model + migrations, config versioning, staff auth/RBAC, append-only hash-chained audit log | Direct UPDATE/DELETE on audit tables fails; chain verifier passes |
| 2. Engine | `get_entitlements`, points/tiers with hysteresis and weekly drop limit, sanctions, offense restrictions, repeat-return ceiling, authority rules | Property tests: baseline never removed, ceiling monotonic, max one tier drop/week, issuer != confirmer |
| 3. Resident shell | Kiosk UI, home screen, tier/lock/appeal screens, i18n, accessibility settings, offline cache | Playwright e2e covers lock reasons and offline lock enforcement |
| 4. Features | Education loop, mock calls, mock commissary | Completing the sample course visibly raises call minutes; attorney calls produce no content records |
| 5. Staff app | Dashboard, confirmation queue, appeals, outlier view, config editor | Full sanction-to-appeal flow passes e2e |
| 6. View-as | Sandbox and live mirror | Sandbox causes zero writes (tested); mirror sessions logged |
| 7. Transparency and stubs | Public log export, welfare flags, out-of-cell log, stubs for text/video/chess/reading/jobs, compliance config and ASSUMPTIONS.md | Export contains no names; jobs opt-out creates no events |
| 8. Hardening | Security checklist, CSP, rate limiting, `.env.example`, kiosk doc, 7-day `simulate-week` run | No secrets in repo; simulation finishes with consistent ledgers and a verified audit chain |

## 14. Working agreement

- Write engine tests first. The engine and audit log are the product, so they get the highest coverage.
- Keep functions small. Business rules live in `api/engine/`, not in routers or UI.
- Never make real network calls from the app. Use mocks and fixtures.
- Keep `docs/DECISIONS.md` current: each decision, why, and what was rejected.
- Ask before deviating from an invariant in section 2. Don't silently relax one.
- Keep this file accurate. When commands or structure change, update the sections above.

### Commands (create in Phase 0, then keep accurate)

```
make db-local # (no Docker) create dev DB roles on a local Postgres
make migrate  # alembic upgrade head
make load-test  # full facility (1,730 kiosks) plus staff screens against a real API (exit 1 if a budget is missed)
make seed-full  # the full 1,920-cell facility with synthetic residents (empty database only)
make daily    # daily job: clean-day points, tier checks (delayed drops), cleanup
make reconcile  # nightly check: balances match their ledgers (exit 2 on mismatch)
make welfare-sweep  # raise/escalate/clear welfare flags (run every 15 min)
make courses-check  # validate course folders under content/courses
make secrets-check  # fail if anything that looks like a secret is committed
make dev      # run api + web + postgres
make test     # pytest + vitest + playwright
make seed     # synthetic residents, staff, config
make lint
make simulate-week   # a simulated week, then every invariant checked (exit 0 = all hold)
make export-public-log   # only if an operator enabled public_log_enabled
```
