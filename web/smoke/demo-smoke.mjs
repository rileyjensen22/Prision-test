// (Demo residents speak English or Spanish, so labels are matched in both.)
// A quick look at a running demo (`make demo`) in a real browser: a resident screen and the staff
// dashboard load and show data. Usage: node smoke/demo-smoke.mjs [http://localhost:8080]
import { chromium } from '@playwright/test'

const base = process.argv[2] ?? 'http://localhost:8080'
const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || undefined })
const problems = []
const check = (ok, what) => {
  console.log(`  ${ok ? '✓' : '✗'} ${what}`)
  if (!ok) problems.push(what)
}

try {
  const kiosk = await browser.newPage({ viewport: { width: 1280, height: 800 } })
  await kiosk.goto(`${base}/resident#device=dev-device-token-A-02`)
  await kiosk.getByTestId('tier-label').waitFor({ timeout: 15_000 })
  check(
    /Tier|Nivel/.test(await kiosk.getByTestId('tier-label').innerText()),
    'a resident screen shows its tier',
  )
  const csp = await kiosk
    .locator('meta[http-equiv="Content-Security-Policy"]')
    .getAttribute('content')
  check(
    Boolean(csp?.includes("default-src 'self'")),
    'the kiosk Content-Security-Policy is in the page',
  )
  check(
    (await kiosk.getByRole('button', { name: /Request staff|Solicitar personal/ }).count()) > 0,
    'Request staff is always on screen',
  )

  const staff = await browser.newPage({ viewport: { width: 1280, height: 800 } })
  await staff.goto(`${base}/staff`)
  await staff.getByLabel('Username').fill('supervisor1')
  await staff.getByLabel('Password').fill('dev-password-not-secret')
  await staff.getByRole('button', { name: 'Sign in' }).click()
  await staff.getByTestId('whoami').waitFor({ timeout: 15_000 })
  check(true, 'a supervisor can sign in')
  await staff.getByTestId('facility-overview').waitFor({ timeout: 15_000 })
  check(true, 'the dashboard shows the facility by hub, line and floor')
  await staff.goto(`${base}/staff/roster`)
  await staff.getByTestId('roster').waitFor({ timeout: 15_000 })
  check(
    (await staff.locator('[data-testid^="row-"]').count()) >= 12,
    'the roster lists the demo residents',
  )
} catch (e) {
  check(false, `unexpected error: ${e.message.split('\n')[0]}`)
} finally {
  await browser.close()
}
process.exit(problems.length ? 1 : 0)
