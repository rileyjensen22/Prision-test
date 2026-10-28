# ISD v1: Resident Device Operating Environment (prototype)

A wall-mounted, touch-first device for single-occupancy cells, a staff dashboard and an API. Residents
spend most of the day alone in a cell; the device gives them education, reading, chess, commissary and
monitored contact with the outside world, and unlocks more of it through ten tiers driven mostly by
automated rules. Every staff decision is visible and auditable.

Version 1 is a **working prototype and demo**, not a production system. Every legal and compliance item is
unverified and needs counsel before any deployment (`docs/ASSUMPTIONS.md`, `docs/compliance-gap-report.md`).
All data in this repository is synthetic: no real names, IDs or records.

## Run the demo (one command)

You need [Docker](https://docs.docker.com/get-docker/) with Compose, about 2 GB of disk and a few minutes the
first time. Nothing else.

```
make demo
```

It builds and starts PostgreSQL, the API and the web app, creates the tables, loads synthetic demo data,
and prints the addresses and logins. Then:

```
make demo-scenario   # plays the whole story for you, step by step
make demo-down       # stop (keeps the data)
make demo-reset      # stop and delete the data
```

- Staff: <http://localhost:8080/staff> (`supervisor1`, `officer1`, `admin1`, `auditor1`; password `dev-password-not-secret`)
- A resident's screen: <http://localhost:8080/resident#device=dev-device-token-A-01> (cells A-01 to A-12)

No `make`? Run `./scripts/demo.sh`, or `docker compose up -d --build`. A guided tour of what to look at is in
[`docs/demo-guide.md`](docs/demo-guide.md). Behind a proxy that inspects TLS, see "Troubleshooting" there.

## Where to read next

| If you want to | Read |
|---|---|
| See the rules the code must keep, and the full specification | `CLAUDE.md` |
| Understand why things are the way they are | `docs/DECISIONS.md` |
| Know what is built, tested and still open | `docs/STATUS.md` |
| Run the system for a facility | `docs/admin-guide.md`, `docs/operations.md` |
| Review security | `docs/security.md`, `docs/threat-model.md` |
| Review the legal and compliance questions | `docs/ASSUMPTIONS.md`, `docs/compliance-gap-report.md` |
| Set up a kiosk | `docs/kiosk.md`, `deploy/kiosk/` |
| See how it is built | `docs/architecture.md`, `docs/facility.md` |

## Develop

Python 3.12, Node 22 and PostgreSQL 16 for the no-Docker path:

```
make db-local        # create the dev database roles (needs a PostgreSQL superuser)
make seed            # migrate, then load synthetic residents, staff and config
make test            # API (pytest, Hypothesis), web (Vitest), browser (Playwright)
make simulate-week   # a simulated week of activity, then every invariant checked
make dev             # the Docker stack with hot reload (web on :5173)
```

| Command | What it does |
|---|---|
| `make demo`, `make demo-scenario`, `make demo-smoke`, `make demo-down`, `make demo-reset`, `make demo-logs` | the Docker demo |
| `make dev` | the Docker stack with hot reload |
| `make db-local`, `make migrate`, `make seed`, `make seed-full` | local database setup; the small demo facility, or the full 1,920-cell one |
| `make test`, `make lint`, `make format` | all tests; ruff, ESLint, Prettier and type checks |
| `make simulate-week` | a simulated week with every invariant checked |
| `make load-test` | the full facility's kiosks plus staff screens against a real API, checked against the budgets |
| `make kiosk-check` | the kiosk provisioning, checked in a Debian container |
| `make daily`, `make reconcile`, `make welfare-sweep` | the scheduled jobs |
| `make courses-check`, `make secrets-check` | validate course folders; fail if a secret is committed |
| `make export-public-log` | write the public log (only if an operator enabled it) |

## Layout

```
api/        FastAPI app: routers, services, the rules engine, mocks for every external system
web/        React app: /resident (the kiosk screen) and /staff (the dashboard)
config/     seed configuration (tiers, points, sanctions, offenses, compliance, facility, ...)
content/    course folders
docs/       specification notes, decisions, status, guides
scripts/    seed, simulate-week, load test, demo, jobs
deploy/     kiosk provisioning, an example reverse-proxy config
```
