# Architecture (current as of Phase 7)

```
resident kiosk (React, /resident)        staff app (React, /staff)
        |  X-Device-Token                       |  Bearer token (sessionStorage)
        v                                       v
   routers/device*.py                  routers/staff_*.py, view_as.py, config.py, audit.py, mock.py
        \                                       /
         \______ services/ (use cases, DB, audit) ______/
                           |
        engine/ (pure rules: no I/O)         interfaces/ + mocks/ (telephony, messaging,
        entitlements, tiers, ceiling,        payments, chess, facility events)
        authority, outliers, welfare,
        sandbox, mirror, public_log
                           |
                      PostgreSQL (append-only: audit_log, config_versions,
                      trust_ledger, out_of_cell_log)
```

Rules of thumb
- **Business rules live in `engine/`** and are tested with Hypothesis. Services load facts, call the engine, and persist.
- **All feature access goes through `get_entitlements`.** A test fails if anything else calls the composer.
- **The kiosk renders one payload, `ResidentView`.** Staff "view as" and the live mirror reuse the same screens with a fixed view.
- **Config is versioned** (`config_versions`): tiers, points, sanctions, offenses, compliance, commissary, courses, welfare, jobs, rec, reading. Every change is an audit entry.
- **Anything private stays private by construction**: attorney calls and messages (guard + DB CHECKs), mirror redaction, the public log allow-list.
- **External services are mocks** behind interfaces; the app makes no network calls.
