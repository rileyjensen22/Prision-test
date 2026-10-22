# ISD v1.1: Phases 9 to 16

Read `CLAUDE.md` first. This file extends it, and every invariant there still applies. Work one phase at a time. Tests must be green before moving on. After each phase, update `docs/DECISIONS.md` and `docs/STATUS.md`.

## Phase 9: Audit before building

1. Run the full test suite, lint, `make simulate-week`, and the audit-chain verifier.
2. Write `docs/STATUS.md`: for each phase 0 to 8, mark it built / partial / missing. List every deviation from an invariant and every TODO.
3. Fix failing tests and invariant violations first.
4. Stop and report to me. List any open questions that need my decision. Don't guess on invariants.

**Done when:** everything is green, STATUS.md is accurate, and the report is delivered.

## New invariants (append to CLAUDE.md section 2)

12. Automated flags (keywords, unusual patterns) only create **review items**. They never create a sanction on their own. A human confirms.
13. Resident-to-resident play has **no free text, no real names, no wagering, no friend lists**. Pairing respects keep-separate records.
14. Device camera frames are never stored or transmitted except as the live call itself. Tamper detection runs on-device on a derived signal (e.g. brightness/variance) and only during an active call.
15. Money paths (trust ledger, job earnings) are append-only. A nightly reconciliation job checks that balances match the ledger and alerts on any mismatch.
16. Reading monitored messages, reviewing monitored calls, and mirroring a device each require a stated reason, and each is audit-logged.
17. Analytics are for evaluation only. They never feed into tier, sanction, or restriction decisions, and there are no individual risk scores.

## Phase 10: Reading and chess

**Reading**
- Reader UI with adjustable text size, bookmarks, progress sync, and offline-cached books.
- Catalog comes only from `approved_content_sources`. General library from T1, expanded from T4. Legal and religious texts stay in the baseline.
- Optional "book completed" points event, config value, default 0.

**Chess**
- `ChessProvider` interface. Engine play runs client-side (WASM). **Check the engine's license before bundling** (Stockfish is GPL), and record the decision in DECISIONS.md.
- Human play (seed: T5+), staff-enabled per unit and per resident, plus a `games` sanction scope.
- Match design: per-match anonymous handles, moves/draw/resign only, no chat, no spectators, no stake or item fields in the schema, rate limits, and a match log.
- `keep_separate` table: matchmaking never pairs residents who appear in each other's records. Residents can leave any match with no penalty.

**Done when:** tests prove no free-text path exists in the match API, keep-separate pairs are never matched, and a `games` sanction blocks human play but not engine play. Baseline reading is unaffected by sanctions.

## Phase 11: Texting and video

**Contacts**
- Resident requests a contact, staff approve it (verification stub), types are `family`, `friend`, `attorney`. No-contact orders override everything.

**Texting**
- Per-tier daily limits, delivery states, and length limits.
- Monitoring queue for non-attorney messages with a role-gated review UI (reason required, audit-logged). Keyword rules in config produce **flags only** (invariant 12).
- Attorney messages are privileged: no staff role can read them, and they never enter the monitoring queue.

**Video**
- `VideoProvider` interface. Implement a WebRTC loopback/demo provider.
- Per-tier weekly minutes, scheduled calls, and recording behind an interface with configurable retention. Attorney video is never recorded.
- Tamper detection per invariant 14. A covered camera ends the call and creates a DEVICE_TAMPER event that goes to supervisor confirmation.

**Done when:** tests show privileged messages are unreadable by any role, a tamper event ends the call without storing frames, and flags never produce sanctions.

## Phase 12: Jobs (voluntary, separate from tiers)

- Listings from mock partners, opt-in/opt-out, and a work log.
- Task sandbox with **non-personal-data task types only**: public-domain transcription, captioning, labeling of non-personal data. No customer-support-style work that exposes third-party data.
- Separate **earnings ledger** with config-driven pay split and deductions. Payouts move to the trust account through the append-only ledger.
- Job access is independent of tier. Whether sanctions can suspend it is a config flag, **default off**, flagged for counsel in ASSUMPTIONS.md.
- Mock partner dashboard: tasks completed, payouts owed.

**Done when:** tests prove declining or quitting a job creates no points event, no sanction, and no entitlement change, and earnings plus trust ledger reconcile in the nightly job.

## Phase 13: Scheduling and welfare

- Schedule model per unit per day: indoor rec, outdoor rec, programs, visits. Entitlements decide eligibility, and T9/T10 outdoor rec comes from the tier matrix.
- Officers log actual out-of-cell time (tap out/in, with bulk actions). "Who is out now" roster. Scheduled-vs-actual discrepancy report. Daily export.
- Welfare flags get per-resident baselines. Staff **must acknowledge** each flag and record the action taken. Unacknowledged flags escalate to a supervisor after a configurable time.

**Done when:** residents below the minimum out-of-cell time surface on the dashboard, and an unacknowledged flag escalates in a time-travel test.

## Phase 14: Education depth

- Course format (Markdown/JSON plus quiz banks) and a validator CLI.
- Prerequisites, save/resume, offline progress sync, certificates (record plus printable view).
- Seed 5 to 8 courses from public or open content only (literacy, numeracy, job readiness, financial literacy, trade basics). At least two in Spanish. Reading-level variants.
- Integrity: question randomization, attempt limits, cooldowns. Points mapping through config.

**Done when:** a course can be added with no code change, validation catches malformed courses, and progress survives going offline mid-lesson.

## Phase 15: Intake, reentry, outcomes

- **Intake flow:** create resident, prior returns (with source), offense categories mapped to restrictions, language/accessibility settings, initial contacts, keep-separate entries, cell assignment. Everything audit-logged.
- **Reentry:** release-date countdown surfaced on the device, checklist (ID documents, housing, employment), reentry courses, and an approved resources directory.
- **Outcomes:** a pseudonymized cohort dashboard (tier progression, course completion, contact frequency, sanction rate) with a field for outcome data entered later from customer records (e.g. 6/12/24 months). Researcher export is pseudonymized. Invariant 17 applies.

**Done when:** export contains no direct identifiers, and nothing in the engine reads from analytics tables (test with an import-boundary check).

## Phase 16: Pilot readiness

- **Linux kiosk provisioning scripts** (not a custom distro): locked-down user, Chromium kiosk via systemd, TTY switching disabled, firewall allowlist, watchdog restart, optional read-only root. Document in `docs/kiosk.md`.
- **Device enrollment and health:** pairing flow, heartbeat (storage, connectivity, last sync, camera/mic status), admin remote lock/restart. OTA update design doc with staged rollout (design only).
- **Operations:** backup/restore drill with a documented result, nightly ledger reconciliation, structured logging.
- **Security:** `docs/threat-model.md` covering device tampering, shoulder-surfing, insider abuse by staff, resident-to-resident coercion through any shared channel, and phishing/fraud aimed at families. Plus a security review checklist and rate limiting everywhere.
- **Scale:** load test with 500 simulated devices.
- **Customer docs:** admin guide, plus a compliance gap report built from ASSUMPTIONS.md (item, owner, status, counsel needed y/n).

**Done when:** a fresh Linux machine can be provisioned to boot straight into the resident UI using only the docs and scripts, the load test passes, and the threat model has a mitigation or accepted-risk note for every item.

## Working agreement

Same as `CLAUDE.md` section 14. Ask before relaxing any invariant. Keep the Commands section of CLAUDE.md accurate as targets are added.
