# ISD v1: Resident Device Operating Environment (prototype)

A demo of a wall-mounted device for single-occupancy cells, a staff dashboard, and an API. Version 1 is a
**working prototype**, not a production system; every legal and compliance item is unverified
(see `docs/ASSUMPTIONS.md`). All data in the repository is synthetic.

- `CLAUDE.md`: the specification and the rules the code must keep (the "invariants").
- `docs/DECISIONS.md`: every design decision, why, and what was rejected.
- `docs/security.md`, `docs/operations.md`, `docs/kiosk.md`, `docs/architecture.md`.

## Quick start (no Docker)

```
make db-local        # create dev database roles (needs a local PostgreSQL superuser)
make seed            # migrate, then load synthetic residents, staff and config
make test            # API (pytest, Hypothesis), web (Vitest), browser (Playwright)
make simulate-week   # a simulated week of activity, then every invariant checked
```

With Docker: `make dev` starts PostgreSQL, the API (:8000) and the web app (:5173).

- Kiosk: `http://localhost:5173/resident#device=dev-device-token-A-01`
- Staff: `http://localhost:5173/staff` (dev logins `officer1`, `supervisor1`, `admin1`, `auditor1`; password `dev-password-not-secret`)

## Commands

| Command | What it does |
|---|---|
| `make dev` | run PostgreSQL, API and web with Docker Compose |
| `make db-local`, `make migrate`, `make seed` | local database setup and synthetic data |
| `make test`, `make lint` | all tests; ruff, ESLint, Prettier, type checks |
| `make simulate-week` | deterministic simulated week with invariant checks |
| `make daily` | the daily job (clean-day points, tier checks, cleanup) |
| `make export-public-log` | write the public log (only if an operator enabled it) |
| `make secrets-check` | fail if anything that looks like a secret is committed |
