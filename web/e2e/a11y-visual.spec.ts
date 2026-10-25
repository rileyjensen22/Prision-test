// UI overhaul checks: accessibility (axe), no horizontal overflow at the three kiosk sizes in both
// languages at large text, and visual regression snapshots of the key screens.
//
// This file sorts first on purpose: it runs against the freshly seeded database, before other
// specs change balances or settings, so the snapshots are deterministic.
//
// Update snapshots after an intended visual change:  npx playwright test a11y-visual --update-snapshots
import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

import { openKiosk, staffLogin } from './helpers'

const SIZES = [
  { name: '1280x800', width: 1280, height: 800 },
  { name: '1024x600', width: 1024, height: 600 },
  { name: '1920x1080', width: 1920, height: 1080 },
]
const RESIDENT_PATHS = [
  '/resident',
  '/resident/locks',
  '/resident/tier',
  '/resident/feature/commissary',
  '/resident/feature/calls',
  '/resident/feature/basic_education',
  '/resident/feature/texting',
  '/resident/jobs',
  '/resident/reentry',
  '/resident/feature/out_of_cell_minimum',
]
const STAFF_PATHS = [
  '/staff',
  '/staff/roster',
  '/staff/confirmations',
  '/staff/appeals',
  '/staff/welfare',
  '/staff/view-as',
  '/staff/config',
  '/staff/styleguide',
]

async function serious(page: Page) {
  const { violations } = await new AxeBuilder({ page }).analyze()
  return violations
    .filter((v) => v.impact === 'serious' || v.impact === 'critical')
    .map((v) => `${v.id}: ${v.help} (${v.nodes.length}) ${v.nodes[0]?.target.join(' ')}`)
}

async function ready(page: Page) {
  await page.getByTestId('kiosk').waitFor()
  await page.locator('main h1, main h2').first().waitFor()
  await page.waitForTimeout(300)
}

for (const who of ['uxen', 'uxes'] as const) {
  for (const mode of ['day', 'night']) {
    test(`axe: kiosk screens have no serious violations (${who}, ${mode})`, async ({ page }) => {
      await page.setViewportSize({ width: 1280, height: 800 })
      for (const path of RESIDENT_PATHS) {
        await openKiosk(page, who, `${path}?mode=${mode}`)
        await ready(page)
        expect(await serious(page), `${path} (${who}, ${mode})`).toEqual([])
      }
    })
  }
}

test('axe: staff pages have no serious violations', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/staff')
  await page.getByLabel('Username').waitFor()
  expect(await serious(page), 'login').toEqual([])
  await staffLogin(page, 'e2e_admin')
  for (const path of STAFF_PATHS) {
    await page.goto(path)
    await page.getByTestId('whoami').waitFor()
    await page.locator('main h1').first().waitFor()
    await page.waitForTimeout(300)
    expect(await serious(page), path).toEqual([])
  }
})

for (const size of SIZES) {
  for (const who of ['uxen', 'uxes'] as const) {
    test(`no horizontal overflow at ${size.name}, large text (${who})`, async ({ page }) => {
      await page.setViewportSize({ width: size.width, height: size.height })
      for (const path of RESIDENT_PATHS) {
        await openKiosk(page, who, path)
        await ready(page)
        const over = await page.evaluate(
          () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
        )
        expect(over, `${path} overflows by ${over}px`).toBeLessThanOrEqual(0)
      }
    })
  }
}

test.describe('visual regression', () => {
  test.use({ viewport: { width: 1280, height: 800 } })
  const opts = { maxDiffPixelRatio: 0.03, animations: 'disabled' as const }

  async function shoot(page: Page, name: string) {
    await expect(page).toHaveScreenshot(name, {
      ...opts,
      mask: [page.locator('time'), page.getByTestId('lock-until'), page.getByTestId('reason-until')],
    })
  }

  test('kiosk home, English, day', async ({ page }) => {
    await openKiosk(page, 'fay', '/resident?mode=day')
    await ready(page)
    await shoot(page, 'home-en-day.png')
  })
  test('kiosk home, Spanish, large text, locked, night', async ({ page }) => {
    await openKiosk(page, 'uxes', '/resident?mode=night')
    await ready(page)
    await shoot(page, 'home-es-large-locked-night.png')
  })
  test('kiosk why is this locked', async ({ page }) => {
    await openKiosk(page, 'alice', '/resident/locks?feature=calls&mode=day')
    await ready(page)
    await shoot(page, 'why-locked-day.png')
  })
  test('kiosk commissary', async ({ page }) => {
    await openKiosk(page, 'hal', '/resident/feature/commissary?mode=day')
    await page.getByTestId('balance').waitFor()
    await shoot(page, 'commissary-day.png')
  })
  test('staff style guide', async ({ page }) => {
    await staffLogin(page, 'e2e_admin', '/staff/styleguide')
    await page.locator('main h1').waitFor()
    await expect(page).toHaveScreenshot('styleguide.png', { ...opts, fullPage: true })
  })
})
