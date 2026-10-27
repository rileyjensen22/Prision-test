# Security checklist (v1 prototype)

Status key: **Done** = implemented and covered by an automated test or check named in the last column.
**Partial** = implemented with a stated limit. **Open** = not built; see the end of this file.
Nothing here is a substitute for an independent security review before real use (CLAUDE.md: v1 is a
demo, and every compliance item is unverified).

## Identity and sessions

| Control | Status | Evidence |
|---|---|---|
| Staff passwords hashed with argon2; a missing user costs the same time as a wrong password | Done | `auth.authenticate`; `test_security.py` (login tests) |
| Signed, expiring staff tokens; role and active flag re-read from the database on every request (deactivation and role changes apply immediately) | Done | `test_tampered_deactivated_and_expired_tokens_are_rejected` |
| Idle timeout: 30-minute token, refreshed every 10 minutes while the person is working | Done | `test_refresh_gives_a_new_working_token…`, `staff/api.test.ts` |
| Login lockout: 5 failures per address and username in 15 minutes; unknown usernames lock the same way; one audit entry per lockout; 60 attempts per minute per address | Done | `test_repeated_failures_lock…`, `test_unknown_usernames…`, `test_login_attempts_per_address…` |
| Mock SSO behind an interface; refused in production | Done | `test_mock_sso`, `test_production_refuses_development_defaults` |
| Kiosk identity: random per-device token, only its hash stored; provisioned in the URL fragment so it never reaches server logs; admin can rotate it (old token dies at once) | Done | `resident/api.test.ts`, `test_device_tokens.py` |
| Staff tokens live in `sessionStorage`, not cookies, so there is no CSRF surface | Done | design; `staff/api.ts` |
| Staff two-step sign-in (TOTP, RFC 6238, replay-protected) with 10 single-use recovery codes; required in production (`STAFF_MFA_REQUIRED`) | Done | `test_staff_security.py` |
| Password change, admin-only password and MFA reset (reason required, audited, temporary password forces a change at next sign-in; old tokens die at once) | Done | `test_staff_security.py`; the accounts screen |

## Access control

| Control | Status | Evidence |
|---|---|---|
| Every route is guarded; the test discovers routes independently (and cross-checks them against the OpenAPI list, so it cannot pass on an empty list) | Done | `test_every_non_public_route_has_a_role_guard` |
| Every protected route refuses anonymous callers and the wrong kind of credential (a staff token on a device route and the reverse) | Done | `test_every_protected_route_rejects_anonymous…` |
| For every route, every role it does not allow gets 403 | Done | `test_every_staff_route_enforces_its_roles` |
| Auditors are read-only; officers cannot see peer comparisons; only admins edit config | Done | route tests in `test_staff_api.py`, `test_rbac_auth.py` |
| Issuer ≠ confirmer ≠ appeal reviewer, enforced in the engine and again by a database CHECK | Done | `tests/engine/test_authority.py`, simulation checks |
| Rate limits per address, per staff member, and per device (in memory, single process) | Partial | `test_device_and_staff_requests_are_rate_limited` |

## Data protection

| Control | Status | Evidence |
|---|---|---|
| Audit log append-only for everyone (trigger plus revoked grants), hash-chained, verifier | Done | `test_audit.py`, simulation |
| Config history, trust ledger, out-of-cell log append-only the same way | Done | `test_phase4_services.py`, `test_phase7_services.py` |
| Attorney calls and messages never recorded or stored: provider told not to keep a copy, guard checks it did not, database CHECK constraints, no content columns, mirror and timeline redaction | Done | `test_phase4_services.py`, `test_phase7_services.py`, simulation (provider recordings equal monitored calls exactly) |
| Public log: field allow-list, salted pseudonyms, week-level dates, small-count suppression, off by default | Done | `test_public_log_jobs.py`, simulation |
| App database user cannot change schema or rewrite append-only tables; migrations use a separate owner user | Done | `test_app_role_has_no_update_delete_grants`; production guard requires different users |
| Sandbox "view as" cannot write (read-only transaction) | Done | `test_the_database_refuses_writes_inside_the_sandbox_transaction` |
| Encryption at rest: AES-256-GCM on message bodies, contact numbers, call recording references and the MFA secret; key id stored with each value; keys from the environment; `scripts/rotate-encryption-key.py` re-encrypts in batches (rotation steps in `isd/services/key_rotation.py`). Contact numbers keep a keyed hash for duplicate checks | Done | `test_crypto.py` |
| Retention jobs driven by `config/compliance.yaml` (periods unset in the real config, so nothing is deleted until counsel sets them); audit, ledger and other protected tables are never touched | Done | `test_retention.py` |
| Disk and backup encryption | **Open** | operator responsibility; see `docs/operations.md` |
| Rate limits in a store shared by every API process (Postgres, sliding window, fails open if the store is down); default in production | Done | `test_shared_ratelimit.py` |

## Application hardening

| Control | Status | Evidence |
|---|---|---|
| API security headers (nosniff, no-store, no-referrer, frame-deny, CSP `default-src 'none'`, permissions policy) | Done | `test_api_responses_carry_security_headers` |
| Kiosk/staff web app CSP in the production build: same-origin scripts, styles, images and API only; inline script blocked | Done | `resident.spec.ts` (CSP test) |
| Request body limit (1 MiB, with or without a declared length) and input length limits | Done | `test_oversized_bodies_are_refused`, `test_login_inputs_have_length_limits` |
| No CORS | Done | `test_cors_is_not_enabled` |
| Production refuses to start with development secrets, development database passwords, shared app/owner users, or mock SSO | Done | `test_the_app_will_not_start_in_production_with_defaults` |
| Secrets: nothing secret in the repository; scanner runs in CI and as a test; forbidden files (`.env`, keys, `var/`) rejected | Done | `scripts/check-secrets.py`, `test_secrets_scan.py` |
| SQL injection: all queries go through SQLAlchemy with bound parameters (the few raw statements are constants) | Done | code review; no string-built SQL with user input |
| XSS: React escapes output; no `dangerouslySetInnerHTML`; the public page escapes every value and has no scripts | Done | grep; `test_pseudonyms_depend_on_the_salt_and_the_page_is_static` |
| Reverse-proxy headers, TLS, HSTS | Partial | example in `deploy/nginx.conf.example` (not run in CI) |
| Dependency audit | Partial | see below |

## Dependency audit (run 2026-10-21)

- **Python (`pip-audit`)**: no known vulnerabilities.
- **npm, production dependencies**: 0 vulnerabilities.
- **npm, all dependencies**: 7 advisories (5 high, 2 moderate), all in the Tailwind CSS 3 build chain (`braces`, `micromatch`, `fast-glob`, `chokidar`, `postcss-selector-parser`). These run only at build time on our own stylesheets and are not part of what ships to a device. The fix is a major upgrade to Tailwind 4, deferred because it changes the configuration format. **Accepted risk until that upgrade.**
- CI runs both audits so new advisories show up.

## Physical and operating-system security

The kiosk is only as locked down as its operating system. `docs/kiosk.md` lists the browser policies and launch flags to apply; they have not been tested on a real device image. Disabling USB ports, boot order, disk encryption, and tamper detection are out of scope for the software.

## Open items and known limits

1. Keys for encryption at rest live in the environment. A cloud KMS or HSM is the production upgrade and is not built.
2. The shared rate limiter fails open when Postgres is unreachable (the API is down then anyway); the in-memory limiter is still used in development.
3. Device tokens are long-lived until rotated; no automatic expiry or hardware attestation.
4. Retention periods are unset pending counsel, so the jobs delete nothing in the real config.
5. Disks and backups must be encrypted by the operator; application-level encryption covers only the columns listed above.
6. The mock providers are not hardened; real telephony, messaging, payment and chess integrations need their own review, especially the attorney-privilege guards.
7. No penetration test, formal threat model, or fuzzing has been done. The simulation and property tests are strong evidence for the rules, not for the network edge.
8. Upgrade Tailwind to clear the build-time advisories.
