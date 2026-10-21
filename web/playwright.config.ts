import { defineConfig } from '@playwright/test'

// CHROMIUM_PATH: use a preinstalled Chromium instead of Playwright's download.
const executablePath = process.env.CHROMIUM_PATH || undefined
const PY = process.env.PYTHON || '../.venv/bin/python'
const E2E_DB_URL =
  process.env.E2E_DATABASE_URL ||
  'postgresql+psycopg://isd_app:isd_app_dev_only@localhost:5432/isd_e2e'

export default defineConfig({
  testDir: './e2e',
  workers: 1, // tests share one seeded database
  webServer: [
    {
      // Seeds a fresh isd_e2e database, then serves the real API against it.
      command: `${PY} ../scripts/e2e-seed.py && ${PY} -m uvicorn isd.main:app --port 8001`,
      cwd: '../api',
      url: 'http://localhost:8001/health',
      env: { DATABASE_URL: E2E_DB_URL },
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      // The production build, so the kiosk CSP is exercised too.
      command: 'npm run build && npm run preview -- --port 4173 --strictPort',
      url: 'http://localhost:4173',
      env: { E2E_API: 'http://localhost:8001' },
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
  use: { baseURL: 'http://localhost:4173', launchOptions: { executablePath } },
})
