# Threat model (v1.2)

Scope: the ISD resident kiosk, the staff dashboard, the API and the database. Everything is a prototype
until an independent security review; this file is the input to that review, not a replacement. Each
threat lists what the software already does (with the test or document that shows it), and either a
further mitigation or a written **accepted risk**. "Needs counsel" and "needs hardware" are marked.

Assets worth protecting, in order: the append-only audit log and ledgers (integrity), attorney
privilege (nothing recorded or read), residents' safety and baseline access, resident and family
personal data, staff credentials, and the kiosk fleet.

Attackers considered: a resident, another resident, a visitor or family member, a staff member acting
alone, two staff acting together, an outsider on the network, someone with physical access to a device.

## 1. Device tampering

| Threat | What exists | Gap or accepted risk |
|---|---|---|
| Resident opens a shell, browser tools, or another site | Kiosk session runs one locked browser (`deploy/kiosk/`, `docs/kiosk.md`): URL allow-list policy, no dev tools, no downloads, no printing, no extensions, fullscreen, restarts on exit. App CSP allows only our origin. Context menu and drag are off. | **Needs hardware.** Policy files and the nftables, TTY and logind settings are tested only as written files (`test_provision.py`), not on a real device. Verify on the first unit (list in `docs/kiosk.md`). |
| Steal or clone a device token | Token is random, only its hash is stored, never in a URL query or server log; rotation kills the old one at once; pairing uses a one-time code that expires. | Accepted: a token read from a device's disk can be replayed from another machine until rotated. Mitigation: rotate on any device swap; staff can pause a device (`device_commands`); heartbeats show a device appearing from nowhere as stale or offline. Hardware attestation is future work. |
| Wrong or changed device clock to extend a cached snapshot | Expiry judged against server time using a stored offset; after `valid_until` the device fails closed. | None known. |
| Cover or aim the camera to hide, or to fake "covered" | Tamper detection runs on-device on a derived brightness signal during an active call only; a covered camera ends the call and creates a *pending* DEVICE_TAMPER that a supervisor must confirm. No frames are stored or sent (invariant 14). | **Needs hardware and counsel.** False positives in dim cells are expected; a supervisor decision is always required. Threshold is config. |
| Damage or unplug a device | DEVICE_DAMAGE needs supervisor confirmation and evidence. A device missing heartbeats for `offline_alert_minutes` raises a staff alert; locks keep applying from the cached snapshot and baseline stays open. | Accepted: an unplugged device cannot show "Request staff". Facility procedures must cover that (the grievance and medical routes also exist on paper). |
| Device kept offline to dodge a lock | Cached lock keeps applying; past `valid_until` it fails closed to baseline only. | None. |

## 2. Shoulder-surfing and reading another resident's screen

- Cells are single-occupancy and the device is wall-mounted; the screen shows only the assigned resident's view.
- No resident personal data is shown on the home screen beyond their own tier, points and locks. Contact names appear only on the calls screen.
- The mirror and sandbox never show attorney calls or legal, grievance, medical or mental-health screens (redacted route `/resident/redacted`).
- **Accepted risk:** an officer or neighbour looking through a cell window can see the screen. Screen privacy filters are a hardware choice (see compliance gap report).
- Inactivity returns the screen to home after `inactivity_return_home_seconds` (default 90); a message thread or reader page does not stay up.

## 3. Insider abuse by staff

| Threat | What exists |
|---|---|
| One officer imposes a significant sanction | Invariant 4: minor immediate sanctions are capped per officer per week; anything larger or supervisor-always needs a different supervisor plus evidence; issuer and confirmer must differ (engine and a database CHECK; property tests). |
| Revenge sanctions, or one officer over-recording | Outlier dashboard (report, sanction and overturn rates versus peers) for supervisors and admins. |
| Rewriting history | Audit log and ledgers are append-only for everyone including admins (trigger plus revoked grants), hash-chained, with a verifier. Fixes are correcting entries. |
| Reading a resident's private messages or watching their device without cause | Monitored message reads, call review and mirroring each need a stated reason and are audit-logged (invariant 16); attorney content is never available. |
| Stolen or shared staff credentials | Argon2 passwords, lockouts, short sessions; **Phase 18 adds TOTP MFA, admin-only password reset and a shared rate-limit store.** Until then: accepted risk, mitigated by the audit log. |
| Admin changes config to loosen rules | Every config change is a new version and an audit entry with the actor and reason; the tier ceiling and protected baseline cannot be edited away by config (invariant 1 is tested against random config). |
| Two staff colluding | Not preventable in software. Detection: outlier view, audit review by the `auditor` role (read-only), the public log if enabled. **Accepted risk.** |
| A database administrator disabling the triggers | Possible for a Postgres superuser. The hash chain detects it; run the verifier on a schedule and keep an off-box copy of the latest hash (`docs/operations.md`). |

## 4. Resident-to-resident coercion through any shared channel

The design removes shared channels instead of policing them (invariant 13):

- **Chess and any game:** no free text, no chat, no names, no friend lists, no spectators, no stakes or items in the schema, anonymous handle fresh per match, only move, draw and resign. Matchmaking refuses `keep_separate` pairs and residents on the same line (so neighbours cannot signal through move patterns). Leaving a match costs nothing, so coercion to play or to throw a game has no lever. Built in Phase 19.
- **Texting and calls:** only to staff-approved external contacts; there is no resident-to-resident messaging, and approved contact lists are individual.
- **Commissary and trust accounts:** per-resident ledgers; no transfers between residents exist in the API. Accepted risk: items bought and handed over outside the software.
- **Work:** voluntary, never affects tier (invariant 7), so pressure to take or decline work gains nothing in the system.
- Accepted risk: coercion outside the device (shouting between cells, the yard) cannot be seen by software. Welfare flags (sudden drop in activity or contact) are the only signal, and they only prompt a person to check in.

## 5. Phishing and fraud aimed at families

| Threat | Mitigation |
|---|---|
| Fake "deposit" or "fee" requests to a resident's family | Families never receive messages from the system; deposits come only through the `PaymentProvider` the facility chooses. The kiosk and staff app never ask anyone for payment details (no payment form exists in the app). Families should be told by the facility, in writing, that the facility will never ask for card details by phone or text. |
| Scammers posing as an incarcerated person to get a deposit | Calls from residents carry a recorded-call notice; the approved contact list is staff-verified. Real verification of numbers is a stub (`ContactVerifier`) and a real process is in the compliance gap report. |
| Scammers posing as staff or an attorney | Attorney contacts need supervisor approval; counsel to confirm a real bar-check process. Attorney status is never inferable from the kiosk by other residents. |
| Deposit disputes and chargebacks | Trust ledger is append-only; reconciliation runs nightly; a mismatch alerts and never self-corrects. |
| Fake "release" or fee scams using public data | The public log is off by default and pseudonymised, with no names or case details. The researcher export is also off by default. |

## 6. Network and platform (outsiders)

- API: every route guarded, rate-limited per address, staff and device; body size limit; security headers; no CORS; production refuses development secrets (`docs/security.md`).
- Transport security and HSTS rely on the reverse proxy (`deploy/nginx.conf.example`; example only).
- **Needs an independent penetration test** before real use. The simulation and property tests are strong evidence for the rules, not for the network edge.

## Review schedule

Revisit this file when any of these change: a real telephony, messaging, payment, video or chess provider is added; the kiosk image changes; a new role is added; retention or encryption settings change; before each pilot.
