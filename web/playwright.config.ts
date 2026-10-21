import { defineConfig } from '@playwright/test'

// Set CHROMIUM_PATH to use a preinstalled Chromium instead of Playwright's download.
const executablePath = process.env.CHROMIUM_PATH || undefined

export default defineConfig({
  testDir: './e2e',
  webServer: {
    command: 'npm run dev -- --port 5173',
    url: 'http://localhost:5173',
    reuseExistingServer: true,
  },
  use: { baseURL: 'http://localhost:5173', launchOptions: { executablePath } },
})
