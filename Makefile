DB_SUPERUSER ?= postgres

.PHONY: db-local migrate dev test seed lint format simulate-week export-public-log install clean

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

lint: $(VENV)/.installed
	$(VENV)/bin/ruff check api scripts
	$(VENV)/bin/ruff format --check api scripts
	cd web && npm run lint

format: $(VENV)/.installed
	$(VENV)/bin/ruff check --fix api scripts
	$(VENV)/bin/ruff format api scripts
	cd web && npm run format

simulate-week: $(VENV)/.installed
	$(PY) scripts/simulate-week.py

export-public-log: $(VENV)/.installed
	$(PY) scripts/export-public-log.py

clean:
	rm -rf $(VENV) var web/node_modules web/dist
