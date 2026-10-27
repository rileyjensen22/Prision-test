DB_SUPERUSER ?= postgres

.PHONY: seed-full load-test db-local migrate daily reconcile welfare-sweep courses-check secrets-check dev test seed lint format simulate-week export-public-log install clean

VENV := .venv
PY := $(VENV)/bin/python

$(VENV)/.installed: api/pyproject.toml
	python3 -m venv $(VENV)
	$(PY) -m pip install -q -e "api[dev]"
	touch $@

install: $(VENV)/.installed
	cd web && npm ci

dev:  ## run api + web + postgres
	docker compose up --build

test: $(VENV)/.installed  ## pytest + vitest + playwright
	cd api && ../$(PY) -m pytest -q
	cd web && npm test
	cd web && npm run e2e

db-local:  ## create dev roles + database on a local Postgres (run as root/postgres)
	su $(DB_SUPERUSER) -c "psql -q -f $(CURDIR)/scripts/db-init.sql"

migrate: $(VENV)/.installed
	cd api && ../$(PY) -m alembic upgrade head

seed: $(VENV)/.installed migrate
	$(PY) scripts/seed.py

seed-full: $(VENV)/.installed migrate  ## the full 1,920-cell facility with synthetic residents (needs an empty database)
	$(PY) scripts/seed-full.py

lint: $(VENV)/.installed
	$(VENV)/bin/ruff check api scripts
	$(VENV)/bin/ruff format --check api scripts
	cd web && npm run lint

format: $(VENV)/.installed
	$(VENV)/bin/ruff check --fix api scripts
	$(VENV)/bin/ruff format api scripts
	cd web && npm run format

daily: $(VENV)/.installed migrate  ## run the daily job (clean-day points, tier checks)
	$(PY) scripts/daily-job.py

reconcile: $(VENV)/.installed migrate  ## check balances against their ledgers (exit 2 on a mismatch)
	$(PY) scripts/reconcile.py

welfare-sweep: $(VENV)/.installed migrate  ## raise, escalate and clear welfare flags now (cron every 15 min)
	$(PY) scripts/welfare-sweep.py

courses-check: $(VENV)/.installed  ## validate every course folder under content/courses
	$(PY) scripts/courses.py validate

secrets-check:  ## fail if the repository contains anything that looks like a secret
	$(PY) scripts/check-secrets.py

load-test: $(VENV)/.installed  ## the full 1,920-cell facility (one kiosk per occupied cell) plus staff screens against a real API; exit 1 if a budget is missed
	$(PY) scripts/load-test.py --scale full

simulate-week: $(VENV)/.installed
	$(PY) scripts/simulate-week.py

export-public-log: $(VENV)/.installed
	$(PY) scripts/export-public-log.py

clean:
	rm -rf $(VENV) var web/node_modules web/dist
