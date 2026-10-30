DB_SUPERUSER ?= postgres

.PHONY: kiosk-check demo-smoke demo demo-scenario demo-down demo-reset demo-logs seed-full load-test db-local migrate daily reconcile welfare-sweep courses-check secrets-check import-books import-law dev test seed lint format simulate-week export-public-log install clean

VENV := .venv
PY := $(VENV)/bin/python

$(VENV)/.installed: api/pyproject.toml
	python3 -m venv $(VENV)
	$(PY) -m pip install -q -e "api[dev]"
	touch $@

install: $(VENV)/.installed
	cd web && npm ci

demo:  ## start Postgres, API and web in Docker with demo data and print the addresses and logins
	./scripts/demo.sh

demo-scenario:  ## play the demo story against the running demo (education -> tier, a lock, an appeal, the audit chain)
	python3 scripts/demo-scenario.py --base http://localhost:$${ISD_WEB_PORT:-8080}/api

kiosk-check:  ## check the kiosk provisioning in a Debian container (packages, firewall syntax, systemd units, browser policy)
	./scripts/kiosk-check.sh

demo-smoke:  ## open the running demo in a real browser and check the main screens load
	cd web && node smoke/demo-smoke.mjs http://localhost:$${ISD_WEB_PORT:-8080}

demo-down:  ## stop the demo (data is kept)
	docker compose down

demo-reset:  ## stop the demo and delete its data
	docker compose down -v

demo-logs:  ## follow the demo's logs
	docker compose logs -f --tail=50

dev:  ## the demo stack with hot reload: API reloads on change, web on http://localhost:5173
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build

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

import-books: $(VENV)/.installed  ## download 20 public-domain books from Project Gutenberg into web/public/books/
	$(PY) scripts/import_books.py --output-dir web/public/books

import-law: $(VENV)/.installed  ## refresh Georgia O.C.G.A. titles 16/17/42 in web/public/law/
	$(PY) scripts/import_law.py --output-dir web/public/law

clean:
	rm -rf $(VENV) var web/node_modules web/dist
