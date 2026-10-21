# Decisions

## Phase 0

- **Seed writes JSON, not Postgres (yet).** The data model arrives in Phase 1; `make seed` produces `var/seed.json` from `/config` plus synthetic people. Rejected: stubbing tables early (would be thrown away).
- **Config is YAML in `/config`, validated by `isd.config_loader`.** Phase 1 moves it into versioned DB tables (invariant 9); YAML stays as the seed source.
- **Python `>=3.12`.** Dev sandbox has 3.13; CI and Docker use 3.12.
- **Makefile uses a local `.venv`** so `make test` needs no Docker/Postgres in Phase 0.
- **Playwright `CHROMIUM_PATH` env override** for sandboxes with a preinstalled browser; CI downloads its own.
- **Stub scripts** for `simulate-week` and `export-public-log` exist so every Makefile target runs; real logic lands in Phases 7-8.
- **Tailwind v3** chosen over v4 for stable PostCSS config.
